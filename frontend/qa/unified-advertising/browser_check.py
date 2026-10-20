"""UI-only contract QA, using explicit local Auth/API and materials transport.

Materials review responses are golden fixtures until B implements the facade.
Old file/source/signal/company/drone routes use the real local QA API/services.
"""

import io
import json
import os
import re
import shutil
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright
from transport import FIXTURES, MaterialsTransport

BASE = "http://127.0.0.1:5181"
OUT = Path(os.environ.get("SAQ_QA_ARTIFACTS", "/tmp/saq-unified-advertising"))
OUT.mkdir(parents=True, exist_ok=True)
results = []


def checkpoint(name):
    results.append({"check": name, "result": "passed"})
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("PASS:", name, flush=True)


def api(page, method, path, data=None, headers=None):
    response = page.request.fetch(
        BASE + path,
        method=method,
        data=data,
        headers={"Authorization": "Bearer qa-local-analyst", **(headers or {})},
    )
    assert response.ok, (path, response.status, response.text())
    return response.json()


def choose(page, notes):
    expect(page.get_by_label("ЖК материала", exact=True)).to_be_enabled()
    page.get_by_label("Решение по гипотезе 1 (R2)", exact=True).select_option(
        "confirmed"
    )
    page.get_by_label("Решение по гипотезе 2 (R3)", exact=True).select_option(
        "insufficient"
    )
    page.get_by_label("Общий комментарий", exact=True).fill(notes)


def screenshot(page, name):
    page.evaluate("""() => {
      let banner = document.getElementById('qa-contract-label');
      if (!banner) { banner = document.createElement('div'); banner.id = 'qa-contract-label'; document.body.append(banner); }
      banner.textContent = 'LOCAL QA · синтетический контракт материалов, не облачный результат';
      banner.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:4px;background:#ffedab;color:#222;font:12px/1.4 sans-serif;z-index:10000;pointer-events:none';
    }""")
    page.screenshot(path=str(OUT / name), full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get("SAQ_CHROMIUM")
        or shutil.which("chromium")
        or p.chromium.executable_path,
        headless=True,
        args=["--no-sandbox"],
    )
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        reduced_motion="reduce",
        accept_downloads=True,
    )
    unexpected = []
    errors = []
    requests = []

    def local_only(route):
        if not route.request.url.startswith(
            (BASE, "http://127.0.0.1:8011", "blob:", "data:")
        ):
            unexpected.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    context.route("**/*", local_only)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append((request.method, request.url)))
    try:
        ad = api(
            page,
            "POST",
            "/api/v1/advertisements",
            {
                "complexId": "demo-complex-04",
                "platform": "LOCAL QA",
                "account": "fictional",
                "sourceUrl": "https://demo.invalid/qa-original",
                "text": FIXTURES["material"]["text"],
                "publishedAt": "2026-10-20T10:00:00Z",
            },
        )
        image_bytes = io.BytesIO()
        Image.new("RGB", (160, 100), "#d7e5df").save(image_bytes, format="PNG")
        image = api(
            page,
            "POST",
            f"/api/v1/advertisements/{ad['id']}/screenshots?expected_version={ad['version']}",
            image_bytes.getvalue(),
            {"Content-Type": "image/png"},
        )
        transport = MaterialsTransport(ad["id"], image["id"])
        page.route("**/api/v1/materials**", transport.handle)

        page.goto(BASE + "/advertising/materials/m1")
        expect(page.get_by_role("button", name="Войти", exact=True)).to_be_visible()
        assert not transport.requests
        page.get_by_label("Электронная почта").fill("qa@example.test")
        page.get_by_label("Пароль", exact=True).fill("local-test-only")
        page.get_by_role("button", name="Войти", exact=True).click()
        expect(
            page.get_by_role("navigation", name="Основная навигация").get_by_role(
                "link", name="Реклама", exact=True
            )
        ).to_have_count(1)
        expect(
            page.get_by_role("button", name="Сохранить проверку", exact=True)
        ).to_be_enabled()
        assert (
            page.get_by_role(
                "button", name=re.compile("Анализировать|Проанализировать")
            ).count()
            == 0
        )
        checkpoint(
            "direct protected material URL; single Advertising navigation; no ordinary AI launch"
        )

        page.get_by_role("button", name="Открыть скриншот", exact=True).click()
        preview = page.get_by_role(
            "img", name="Оригинальный скриншот источника для проверки аналитиком"
        )
        expect(preview).to_be_visible()
        assert preview.evaluate("node => node.complete && node.naturalWidth === 160")
        expect(
            page.get_by_text("Приоритет проверки: Высокий · 82", exact=True)
        ).to_be_visible()
        expect(page.get_by_text("10 · Зелёная зона", exact=True)).to_be_visible()
        transport.occurrence_error = True
        page.get_by_role("button", name="Следующие публикации").click()
        expect(page.get_by_role("alert")).to_be_visible()
        page.get_by_role("button", name="Повторить", exact=True).click()
        expect(
            page.get_by_label("Публикация", exact=True).locator("option")
        ).to_have_count(3)
        page.get_by_label("Публикация", exact=True).select_option("o3")
        expect(
            page.get_by_text("DEMO: третий сохранённый оригинал", exact=True)
        ).to_be_visible()
        page.get_by_role("button", name="Показать оригинал цитаты").first.click()
        expect(page.get_by_label("Публикация", exact=True)).to_have_value("o1")
        expect(page.get_by_role("region", name="Оригиналы материала")).to_be_focused()
        checkpoint(
            "authorized private image; independent priority/risk; originals pagination failure/retry; quote-to-original focus"
        )

        choose(page, "LOCAL QA: сверены оригинал и выбранный ЖК")
        for width, height in [(1440, 900), (375, 812), (320, 700)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), width
            panels = page.locator(".advertising .ad-panel")
            expected_padding = "24px" if width == 1440 else "18px"
            assert (
                panels.first.evaluate("node => getComputedStyle(node).paddingLeft")
                == expected_padding
            )
            assert (
                page.locator(".ad-grid").evaluate(
                    "node => parseFloat(getComputedStyle(node).gap)"
                )
                >= 16
            )
            assert page.locator(".advertising progress").count() == 0
            expect(page.get_by_label("Общий комментарий", exact=True)).to_have_value(
                "LOCAL QA: сверены оригинал и выбранный ЖК"
            )
            screenshot(page, f"material-review-{width}-test-adapters.png")
        checkpoint(
            "1440/375/320; 24/18 px internal padding, 16–24 px gaps; no page overflow or construction progress; draft survives resize"
        )

        transport.mode = "conflict"
        page.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Данные изменились")
        expect(
            page.get_by_role("button", name="Сохранить проверку", exact=True)
        ).to_be_disabled()
        page.get_by_role("button", name="Обновить материал и ЖК", exact=True).click()
        acknowledgment = page.get_by_role(
            "checkbox", name=re.compile("Я сверил обновлённые данные")
        )
        expect(acknowledgment).to_be_visible()
        expect(page.get_by_label("Общий комментарий", exact=True)).to_have_value(
            "LOCAL QA: сверены оригинал и выбранный ЖК"
        )
        expect(
            page.get_by_label("Решение по гипотезе 1 (R2)", exact=True)
        ).to_have_value("confirmed")
        assert len(transport.reviews) == 1
        acknowledgment.click()
        assert len(transport.reviews) == 1
        page.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(page.get_by_text("35 · Жёлтая зона", exact=True)).to_be_visible()
        assert len(transport.reviews) == 2
        assert transport.reviews[1]["revisionId"] == "revision-refreshed"
        assert transport.reviews[1]["expectedVersion"] == 2
        assert transport.reviews[1]["requestId"] != transport.reviews[0]["requestId"]
        assert not any(
            method == "POST"
            and re.search(r"/factors/|/hypotheses/.*/decision|/analyze$", url)
            for method, url in requests
        )
        checkpoint(
            "409 retains draft; explicit refresh+acknowledgment; one atomic review request; fixed golden risk response, no factor/AI calls"
        )

        page.get_by_label("Общий комментарий", exact=True).fill(
            "LOCAL QA: безопасный повтор при потере ответа"
        )
        transport.mode = "lost_response"
        page.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Нет связи")
        count = len(transport.reviews)
        page.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(page.get_by_text("Проверка сохранена.", exact=False)).to_be_visible()
        assert len(transport.reviews) == count + 1
        assert transport.reviews[-1] == transport.reviews[-2]
        transport.mode = "invalid"
        page.get_by_label("Общий комментарий", exact=True).fill(
            "LOCAL QA: недостаточное доказательство"
        )
        page.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("недостаточно доказательств")
        assert "PRIVATE PROVIDER DETAILS" not in page.locator("body").inner_text()
        expect(page.get_by_label("Общий комментарий", exact=True)).to_have_value(
            "LOCAL QA: недостаточное доказательство"
        )
        checkpoint(
            "lost response keeps identical requestId/payload on manual retry; 422 keeps draft and hides provider details"
        )

        page.goto(BASE + "/advertising/materials/failed")
        retry = page.get_by_role(
            "button", name="Повторить после ошибки анализа", exact=True
        )
        expect(retry).to_be_enabled()
        transport.mode = "quota"
        retry.click()
        expect(page.get_by_role("alert")).to_contain_text("лимит")
        assert len(transport.retries) == 1
        retry.click()
        expect(
            page.get_by_text("Ожидает автоматического анализа", exact=True)
        ).to_be_visible()
        assert transport.retries[-1] == transport.retries[-2]
        expect(
            page.get_by_role(
                "button", name="Повторить после ошибки анализа", exact=True
            )
        ).to_have_count(0)
        page.goto(BASE + "/advertising/materials/video")
        expect(
            page.get_by_text("Автоанализ этого формата недоступен", exact=True)
        ).to_be_visible()
        expect(
            page.get_by_text("Приоритет проверки: Ещё не оценено", exact=True)
        ).to_be_visible()
        expect(
            page.get_by_role("link", name="Открыть внешний материал ↗")
        ).to_be_visible()
        assert (
            page.locator(
                "video, iframe, img[src^='http'], a[href^='javascript:']"
            ).count()
            == 0
        )
        assert len(transport.retries) == 2
        page.goto(BASE + "/advertising/materials/queued")
        expect(
            page.get_by_text("Ожидает доступной квоты анализа", exact=True)
        ).to_be_visible()
        checkpoint(
            "retry only for failed/canRetry; quota and queued states; null priority; unsupported video and no external media fetch"
        )

        page.goto(BASE + "/advertising")
        tabs = page.get_by_role("navigation", name="Разделы рекламы")
        expect(tabs.get_by_role("link")).to_have_count(2)
        expect(
            page.get_by_role("heading", name="Поиск материалов", exact=True)
        ).to_be_visible()
        expect(page.get_by_text("Публикаций: 3", exact=True).first).to_be_visible()
        page.get_by_role("button", name="Следующие материалы").click()
        expect(page).to_have_url(re.compile("cursor=2"))
        page.get_by_label("Необходимость проверки", exact=True).select_option(
            "reviewed"
        )
        expect(
            page.get_by_role(
                "heading", name="DEMO — ранее проверенный материал", exact=True
            )
        ).to_be_visible()
        assert "cursor=" not in page.url
        page.go_back()
        expect(page).to_have_url(re.compile("cursor=2"))
        page.go_forward()
        page.reload()
        expect(page.get_by_label("Необходимость проверки", exact=True)).to_have_value(
            "reviewed"
        )
        transport.list_error = True
        page.get_by_role("button", name="Обновить материалы", exact=True).click()
        expect(page.get_by_role("alert")).to_be_visible()
        transport.list_error = False
        page.get_by_role("button", name="Повторить", exact=True).click()
        expect(
            page.get_by_role(
                "heading", name="DEMO — ранее проверенный материал", exact=True
            )
        ).to_be_visible()
        transport.empty = True
        page.get_by_role("button", name="Обновить материалы", exact=True).click()
        expect(
            page.get_by_role("heading", name="Материалов пока нет", exact=True)
        ).to_be_visible()
        transport.empty = False
        checkpoint(
            "two tabs; grouped publication count; server filters and cursor reset; back/forward/reload; list error/retry/empty"
        )

        page.goto(BASE + "/advertising?view=sources")
        expect(
            page.get_by_role("navigation", name="Разделы рекламы").get_by_role("link")
        ).to_have_count(2)
        page.get_by_label("Название источника", exact=True).fill("LOCAL QA — источник")
        page.get_by_label("Тип источника", exact=True).select_option("web_search")
        page.get_by_label("Поисковый запрос", exact=True).fill(
            "квартиры Усть-Каменогорск"
        )
        page.get_by_role("button", name="Сохранить источник", exact=True).click()
        expect(
            page.get_by_text("Источник сохранён. Настройки применены.", exact=True)
        ).to_be_visible()
        page.get_by_role("button", name="Получить публикации", exact=True).click()
        expect(page.get_by_text("Сбор завершён:", exact=False)).to_be_visible()
        page.get_by_text("История запусков", exact=True).click()
        expect(
            page.get_by_role("heading", name="Сбор завершён", exact=True)
        ).to_be_visible()
        for width, height in [(1440, 900), (375, 812), (320, 700)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), width
        screenshot(page, "sources-320-test-adapters.png")
        checkpoint(
            "source configuration/schedule controls and collection/history use real local services; 1440/375/320"
        )

        page.goto(BASE + f"/advertisements/{ad['id']}?source=qa-origin")
        expect(page).to_have_url(
            BASE + f"/advertising/legacy/advertisement/{ad['id']}?source=qa-origin"
        )
        expect(page.locator(".ad-text")).to_have_text(FIXTURES["material"]["text"])
        findings = api(page, "GET", "/api/v1/monitoring/items?limit=20")["items"]
        assert findings
        page.goto(BASE + f"/monitoring?item={findings[0]['id']}&status=new")
        expect(page).to_have_url(re.compile("/advertising/legacy/monitoring/"))
        expect(
            page.get_by_role("heading", name="Оригинал и прежняя история", exact=True)
        ).to_be_visible()
        page.goto(BASE + "/monitoring?view=runs")
        expect(page).to_have_url(re.compile("view=sources"))
        expect(
            page.get_by_role("heading", name="Сбор завершён", exact=True)
        ).to_be_visible()
        checkpoint(
            "legacy advertisement/finding IDs and query retained; old runs open inside Sources, without guessing material IDs"
        )

        page.goto(BASE + "/complexes")
        expect(
            page.get_by_role("button", name="Показать карту города", exact=True)
        ).to_be_visible()
        expect(page.get_by_role("table")).to_be_visible()
        assert page.locator("progress").count() == 0
        page.goto(BASE + "/companies")
        expect(
            page.get_by_role("heading", name="Организации", exact=True)
        ).to_be_visible()
        page.goto(BASE + "/drone-inspections")
        expect(page.get_by_role("heading", name=re.compile("Дрон"))).to_be_visible()
        page.goto(BASE + "/signals/new?complex=demo-complex-01")
        page.get_by_label("Заголовок сигнала", exact=True).fill(
            "LOCAL QA — прежний PDF"
        )
        page.get_by_label("Основание для проверки", exact=True).fill(
            "LOCAL QA: отдельная проверка сохранности старого PDF, не результат фиктивного materials review"
        )
        page.get_by_role("button", name="Создать черновик", exact=True).click()
        expect(page).to_have_url(re.compile("/signals/[^/]+$"))
        with page.expect_download() as download:
            page.get_by_role("button", name="Скачать PDF", exact=True).click()
        target = OUT / "preserved-local-signal.pdf"
        download.value.save_as(target)
        assert target.read_bytes().startswith(b"%PDF-")
        checkpoint(
            "registry/city-map entry, companies, drone and real local legacy signal/PDF preserved; no progress controls"
        )

        page.goto(BASE + "/advertising")
        page.get_by_role("button", name="Выйти", exact=True).click()
        expect(page.get_by_role("button", name="Войти", exact=True)).to_be_visible()
        page.reload()
        expect(page.get_by_role("navigation", name="Основная навигация")).to_have_count(
            0
        )
        assert not errors, errors
        assert not unexpected, unexpected
        assert not any("qa-local-analyst" in url for _, url in requests)
        (OUT / "transport-review-payloads.json").write_text(
            json.dumps(transport.reviews, ensure_ascii=False, indent=2)
        )
        checkpoint(
            "logout/reload, no page errors or external requests; no tokens in URLs; synthetic materials adapter only"
        )
    except Exception:
        page.screenshot(path=str(OUT / "failure.png"), full_page=True)
        (OUT / "failure.txt").write_text(page.locator("body").inner_text())
        raise
    finally:
        context.close()
        browser.close()
