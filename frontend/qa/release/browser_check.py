"""Opt-in Chromium checks against the LOCAL QA servers, never the published site.

Uses the existing Playwright installation; see README.md for setup and boundaries.
"""

import io
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:5181"
OUT = Path(os.environ.get("SAQ_QA_ARTIFACTS", "/tmp/saq-release-browser"))
OUT.mkdir(parents=True, exist_ok=True)
results = []
(OUT / "results.json").write_text("[]")


def checkpoint(name, detail):
    results.append({"check": name, "result": "passed", "detail": detail})
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("PASS:", name, detail, flush=True)


def login(page):
    page.get_by_label("Электронная почта").fill("qa@example.test")
    page.get_by_label("Пароль", exact=True).fill("local-test-only")
    page.get_by_role("button", name="Войти", exact=True).click()
    expect(page.get_by_role("navigation", name="Основная навигация")).to_be_visible()


def error_once(
    page,
    pattern,
    status=503,
    code="TEST_UNAVAILABLE",
    body=None,
    content_type="application/json",
):
    state = {"used": False}

    def handler(route):
        if state["used"]:
            route.fallback()
            return
        state["used"] = True
        route.fulfill(
            status=status,
            content_type=content_type,
            body=body or json.dumps({"code": code, "message": "TEST ONLY"}),
        )

    page.route(pattern, handler)
    return state


def limited_history(route):
    response = route.fetch(url=re.sub(r"limit=(50|100)", "limit=2", route.request.url))
    route.fulfill(response=response)


def api(page, method, path, data=None):
    response = page.request.fetch(
        BASE + path,
        method=method,
        data=data,
        headers={"Authorization": "Bearer qa-local-analyst"},
    )
    assert response.ok, (method, path, response.status, response.text())
    return response.json()


def mutate_complex(page):
    current = api(page, "GET", "/api/v1/complexes/demo-complex-04")
    return api(
        page,
        "POST",
        "/api/v1/complexes/demo-complex-04/factors/decision",
        {
            "code": "R6",
            "decision": "unknown",
            "evidenceIds": [],
            "expectedVersion": current["version"],
            "notes": "LOCAL TEST concurrent reviewer",
        },
    )


with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get("SAQ_CHROMIUM")
        or shutil.which("chromium")
        or p.chromium.executable_path,
        headless=True,
        args=["--no-sandbox"],
    )
    context = browser.new_context(
        viewport={"width": 1366, "height": 768}, accept_downloads=True
    )
    unexpected = []
    errors = []
    requests = []

    def local_only(route):
        url = urlsplit(route.request.url)
        if url.hostname not in ["127.0.0.1", "localhost"] and url.scheme not in [
            "blob",
            "data",
        ]:
            unexpected.append(url.hostname)
            route.abort()
        else:
            route.continue_()

    context.route("**/*", local_only)
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append((r.method, r.url)))
    try:
        page.goto(BASE + "/complexes/demo-complex-04?tab=ads")
        expect(page.get_by_role("heading", name="Вход в SAQ QURYLYS")).to_be_visible()
        assert page.get_by_role("navigation").count() == 0
        page.get_by_label("Электронная почта").fill("qa@example.test")
        page.get_by_label("Пароль", exact=True).fill("wrong-test-password")
        page.get_by_role("button", name="Войти", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Не удалось войти")
        expect(page.get_by_label("Пароль", exact=True)).to_have_value("")
        login(page)
        expect(
            page.get_by_role("heading", name="Горная мозаика", exact=True)
        ).to_be_visible()
        page.get_by_role("button", name="Выйти", exact=True).click()
        expect(page.get_by_role("heading", name="Вход в SAQ QURYLYS")).to_be_visible()
        page.reload()
        assert page.get_by_role("navigation").count() == 0
        login(page)
        checkpoint(
            "auth",
            "Direct protected URL, failed login, successful local adapter login, logout and reload",
        )

        page.get_by_role("link", name="Реестр ЖК", exact=True).click()
        page.get_by_label("Поиск ЖК").fill("Горная мозаика")
        page.get_by_role("button", name="Найти", exact=True).click()
        expect(page.get_by_role("link", name="Карточка", exact=True)).to_have_count(1)
        page.get_by_role("link", name="Карточка", exact=True).click()
        page.go_back()
        expect(page.get_by_label("Поиск ЖК")).to_have_value("Горная мозаика")
        page.reload()
        expect(page.get_by_label("Поиск ЖК")).to_have_value("Горная мозаика")
        page.go_forward()
        expect(
            page.get_by_role("heading", name="Горная мозаика", exact=True)
        ).to_be_visible()
        page.go_back()
        page.get_by_label("Поиск ЖК").fill("нет-такого-объекта")
        page.get_by_role("button", name="Найти", exact=True).click()
        expect(page.get_by_role("heading", name="ЖК не найдены")).to_be_visible()
        page.get_by_label("Поиск ЖК").fill("")
        page.get_by_role("button", name="Найти", exact=True).click()
        page.get_by_label("Город", exact=True).select_option("Риддер")
        page.get_by_label("Приоритет", exact=True).select_option("GREEN")
        expect(page.get_by_role("region", name="Жилые комплексы")).to_contain_text(
            "Риддер"
        )
        page.get_by_label("Город", exact=True).select_option("")
        page.get_by_label("Приоритет", exact=True).select_option("")
        page.route("**/api/v1/complexes?*", limited_history)
        page.reload()
        page.get_by_role("button", name="Следующая страница").click()
        expect(page).to_have_url(re.compile(r"cursor=2"))
        page.reload()
        expect(page).to_have_url(re.compile(r"cursor=2"))
        page.get_by_role("button", name="В начало", exact=True).click()
        page.unroute("**/api/v1/complexes?*", limited_history)
        checkpoint(
            "catalog",
            "Search/filters/empty; card → back/forward/reload preserves search and page cursor",
        )

        page.get_by_role("link", name="Объявления", exact=True).click()
        page.get_by_role("button", name="Добавить объявление").click()
        writes_before = len([r for r in requests if r[0] == "POST"])
        page.get_by_role("button", name="Сохранить объявление").click()
        assert len([r for r in requests if r[0] == "POST"]) == writes_before
        page.get_by_label("Жилой комплекс", exact=True).select_option("demo-complex-04")
        page.get_by_label("Площадка", exact=True).fill("DEMO LOCAL QA")
        page.get_by_label("Аккаунт / автор").fill("fictional-qa")
        page.get_by_label("Оригинальная ссылка").fill("https://demo.invalid/qa-release")
        page.get_by_label("Дата публикации", exact=True).fill("2026-10-15T15:45")
        original = "  DEMO: Горная мозаика.\nВнесите депозит 135 000 тенге.  "
        page.get_by_label("Текст объявления").fill(original)
        error_once(page, "**/api/v1/advertisements")
        page.get_by_role("button", name="Сохранить объявление").click()
        expect(page.get_by_role("alert")).to_be_visible()
        expect(page.get_by_label("Текст объявления")).to_have_value(original)
        page.get_by_role("button", name="Сохранить объявление").click()
        expect(page.get_by_role("heading", name="Новое объявление")).to_have_count(0)
        ads = api(page, "GET", "/api/v1/advertisements?limit=100")["items"]
        ad = next(a for a in ads if a["account"] == "fictional-qa")
        assert ad["text"] == original
        page.goto(BASE + "/complexes/demo-complex-04?tab=ads")
        card = page.locator("article.advertisement-card").filter(
            has_text="fictional-qa"
        )
        expect(card.locator(".ad-text")).to_have_text(original)
        source = card.get_by_role("link", name="Открыть источник")
        expect(source).to_have_attribute("href", "https://demo.invalid/qa-release")
        expect(source).to_have_attribute("rel", "noopener noreferrer")
        card.get_by_role("button", name="Скриншоты и AI-анализ").click()
        panel = card.get_by_role("region", name="Анализ объявления")
        checkpoint(
            "new advertisement",
            "Native validation; failed save → retry; exact whitespace/newlines persisted by real local API",
        )

        held = []
        page.route(
            "**/api/v1/advertisements/*/analyze", lambda route: held.append(route)
        )
        panel.get_by_role("button", name="Анализировать выбранный источник").click()
        expect(panel.get_by_role("button", name="Выполняется…")).to_be_disabled()
        assert held
        held.pop().continue_()
        page.unroute("**/api/v1/advertisements/*/analyze")
        expect(panel.get_by_role("button", name="Рассмотреть гипотезу")).to_be_visible()
        assert api(page, "GET", "/api/v1/complexes/demo-complex-04/risk")["score"] == 10
        checkpoint(
            "AI success/loading",
            "Real services with MockTransport; hypothesis leaves score at 10",
        )

        for code, status, message in [
            ("AI_MODEL_UNAVAILABLE", 503, "модель Gemini недоступна"),
            ("AI_PROVIDER_QUOTA", 429, "Лимит Gemini исчерпан"),
        ]:
            error_once(page, "**/api/v1/advertisements/*/analyze", status, code)
            panel.get_by_role("button", name="Анализировать выбранный источник").click()
            expect(panel.get_by_role("alert")).to_contain_text(message)
        page.route("**/api/v1/advertisements/*/analyze", lambda route: route.abort())
        panel.get_by_role("button", name="Анализировать выбранный источник").click()
        expect(panel.get_by_role("alert")).to_contain_text("Нет связи с сервером")
        page.unroute("**/api/v1/advertisements/*/analyze")
        assert api(page, "GET", "/api/v1/complexes/demo-complex-04/risk")["score"] == 10
        checkpoint(
            "AI failures",
            "Model/quota typed errors and network abort; original ad and score preserved",
        )

        upload = panel.get_by_label("Добавить скриншот")
        upload.set_input_files(
            {"name": "wrong.txt", "mimeType": "text/plain", "buffer": b"not an image"}
        )
        panel.get_by_role("button", name="Загрузить", exact=True).click()
        expect(panel.get_by_role("alert")).to_contain_text("JPEG, PNG или WebP")
        before = len([r for r in requests if "/screenshots" in r[1] and r[0] == "POST"])
        upload.set_input_files(
            {
                "name": "large.png",
                "mimeType": "image/png",
                "buffer": b"x" * (6 * 1024 * 1024 + 1),
            }
        )
        panel.get_by_role("button", name="Загрузить", exact=True).click()
        expect(panel.get_by_role("alert")).to_contain_text("Максимальный размер")
        assert (
            len([r for r in requests if "/screenshots" in r[1] and r[0] == "POST"])
            == before
        )
        upload.set_input_files(
            {
                "name": "broken.png",
                "mimeType": "image/png",
                "buffer": b"\x89PNG\r\n\x1a\nBROKEN",
            }
        )
        panel.get_by_role("button", name="Загрузить", exact=True).click()
        expect(panel.get_by_role("alert")).to_contain_text("JPEG, PNG или WebP")
        image = io.BytesIO()
        Image.new("RGB", (80, 40), "white").save(image, "PNG")
        upload.set_input_files(
            {
                "name": "synthetic.png",
                "mimeType": "image/png",
                "buffer": image.getvalue(),
            }
        )
        panel.get_by_role("button", name="Загрузить", exact=True).click()
        expect(panel.get_by_label("Источник анализа")).not_to_have_value("")
        panel.get_by_role("button", name="Открыть скриншот").click()
        expect(panel.get_by_role("img")).to_be_visible()
        panel.get_by_label("Источник анализа").select_option("")
        checkpoint(
            "screenshots",
            "Wrong MIME, >6 MiB rejected; corrupt PNG rejected; valid PNG stored/read with private local API",
        )

        panel.get_by_role("button", name="Рассмотреть гипотезу").click()
        panel.get_by_label("Обоснование", exact=True).fill(
            "LOCAL TEST: принять только к проверке источника"
        )
        panel.get_by_role("button", name="Сохранить решение", exact=True).click()
        expect(
            panel.get_by_text("Принято для проверки доказательства", exact=True)
        ).to_be_visible()
        assert api(page, "GET", "/api/v1/complexes/demo-complex-04/risk")["score"] == 10
        panel.get_by_role("link", name="К доказательству").click()
        evidence = page.locator("article.evidence-card").filter(has_text="135 000")
        evidence.get_by_role("button", name="Проверить источник", exact=True).click()
        evidence.get_by_label(
            "Источник содержит прямое предложение внести платёж"
        ).check()
        evidence.get_by_label("Обоснование решения").fill(
            "LOCAL TEST: сверено с точным оригиналом"
        )
        evidence.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(evidence.get_by_text("Источник проверен", exact=True)).to_be_visible()
        assert api(page, "GET", "/api/v1/complexes/demo-complex-04/risk")["score"] == 10
        page.get_by_role("button", name="Решение по фактору R2", exact=True).click()
        risk = page.get_by_role("complementary", name="Приоритет и решения по факторам")
        risk.get_by_label("Решение", exact=True).select_option("confirmed")
        risk.get_by_role("checkbox", name=re.compile("135 000")).check()
        risk.get_by_label("Обоснование", exact=True).fill(
            "LOCAL TEST: отдельное подтверждение R2"
        )
        risk.get_by_role("button", name="Сохранить решение", exact=True).click()
        expect(risk.locator(".risk-total")).to_contain_text("35")
        checkpoint(
            "human review separation",
            "AI acceptance 10 → source review 10 → explicit R2 35; backend calculates risk",
        )

        page.get_by_role("link", name="Создать сигнал").click()
        page.get_by_label("Заголовок сигнала").fill("DEMO — LOCAL release signal")
        reason = "Сохранить введённый текст при конфликте версии"
        page.get_by_label("Основание для проверки").fill(reason)
        mutate_complex(page)
        page.get_by_role("button", name="Создать черновик").click()
        expect(page.get_by_role("alert")).to_contain_text("Данные изменились")
        page.get_by_role("button", name="Обновить данные ЖК").click()
        expect(page.get_by_label("Основание для проверки")).to_have_value(reason)
        expect(page.get_by_label("Заголовок сигнала")).to_have_value(
            "DEMO — LOCAL release signal"
        )
        page.get_by_role("button", name="Создать черновик").click()
        expect(page).to_have_url(re.compile(r"/signals/[^/?]+$"))
        signal_path = urlsplit(page.url).path
        signal = api(page, "GET", "/api/v1" + signal_path)
        assert signal["status"] == "draft"
        page.get_by_label("Обоснование решения").fill("LOCAL TEST submit")
        page.get_by_role("button", name="Сохранить решение по сигналу").click()
        expect(page.locator(".page-description")).to_have_text("На проверке")
        concurrent = api(page, "GET", "/api/v1" + signal_path)
        api(
            page,
            "POST",
            "/api/v1" + signal_path + "/decision",
            {
                "action": "return",
                "expectedVersion": concurrent["version"],
                "notes": "LOCAL TEST other reviewer",
            },
        )
        page.get_by_label("Обоснование решения").fill(
            "LOCAL TEST сохранить после конфликтующего решения"
        )
        page.get_by_role("button", name="Сохранить решение по сигналу").click()
        expect(page.get_by_role("alert")).to_contain_text("Данные изменились")
        page.get_by_role("button", name="Обновить", exact=True).click()
        expect(page.get_by_label("Обоснование решения")).to_have_value(
            "LOCAL TEST сохранить после конфликтующего решения"
        )
        expect(page.locator(".page-description")).to_have_text("Возвращён")
        page.get_by_role("button", name="Сохранить решение по сигналу").click()
        expect(page.locator(".page-description")).to_have_text("На проверке")
        page.get_by_label("Обоснование решения").fill("LOCAL TEST return")
        page.get_by_role("button", name="Сохранить решение по сигналу").click()
        expect(page.locator(".page-description")).to_have_text("Возвращён")
        page.get_by_label("Обоснование решения").fill("LOCAL TEST resubmit")
        page.get_by_role("button", name="Сохранить решение по сигналу").click()
        expect(page.locator(".page-description")).to_have_text("На проверке")
        page.get_by_label("Действие по сигналу").select_option("confirm")
        page.get_by_label("Обоснование решения").fill("LOCAL TEST confirmed by human")
        page.get_by_role("button", name="Сохранить решение по сигналу").click()
        expect(page.locator(".page-description")).to_have_text("Подтверждён аналитиком")
        checkpoint(
            "signal lifecycle/conflict",
            "Real API draft → submit → return → resubmit → confirm; stale creation preserves reason/title and refreshes version",
        )

        history = page.locator("section").filter(
            has=page.get_by_role("heading", name="История сигнала", exact=True)
        )
        page.route("**/api/v1/signals/*/history?*", limited_history)
        held_history = []
        page.route(
            "**/api/v1/signals/*/history?*", lambda route: held_history.append(route)
        )
        page.get_by_role("button", name="Обновить", exact=True).click()
        expect(history.get_by_role("status")).to_contain_text("Загружаем данные")
        page.unroute("**/api/v1/signals/*/history?*")
        page.route("**/api/v1/signals/*/history?*", limited_history)
        held_history.pop().continue_()
        page.get_by_role("button", name="Обновить", exact=True).click()
        history.get_by_role("button", name="Далее", exact=True).click()
        expect(
            history.get_by_role("button", name="В начало", exact=True)
        ).to_be_visible()
        error_once(
            page, "**/api/v1/signals/*/history?*", 503, "FIRESTORE_INDEX_REQUIRED"
        )
        page.get_by_role("button", name="Обновить", exact=True).click()
        expect(history.get_by_role("alert")).to_contain_text("индексов Firestore")
        history.get_by_role("button", name="Повторить", exact=True).click()
        expect(history.get_by_role("alert")).to_have_count(0)
        checkpoint(
            "history",
            "Actual audit pagination (limit reduced to 2 in transport); index error → retry without extra writes",
        )

        downloads = []
        page.on("download", lambda download: downloads.append(download))
        error_once(
            page,
            "**/api/v1/signals/*/report",
            200,
            body="<html>TEST error page</html>",
            content_type="text/html",
        )
        page.get_by_role("button", name="Скачать PDF").click()
        expect(page.get_by_role("alert")).to_contain_text("Сервер не вернул PDF")
        assert not downloads
        error_once(page, "**/api/v1/signals/*/report", 503, "PDF_RENDER_FAILED")
        page.get_by_role("button", name="Скачать PDF").click()
        expect(page.get_by_role("alert")).to_contain_text("Не удалось сформировать PDF")
        with page.expect_download() as download_info:
            page.get_by_role("button", name="Скачать PDF").click()
        target = OUT / "local-real-server.pdf"
        download_info.value.save_as(target)
        assert target.read_bytes().startswith(b"%PDF-")
        checkpoint(
            "PDF",
            "HTML response blocked; typed render error; retry downloads actual local WeasyPrint PDF",
        )

        for width, height in [(1366, 768), (375, 812), (320, 700)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), width
            page.get_by_role("link", name="К содержимому").focus()
            page.keyboard.press("Enter")
            expect(page.get_by_role("main")).to_be_focused()
        page.screenshot(
            path=str(OUT / "mobile-signal-test-adapters.png"), full_page=True
        )
        checkpoint(
            "mobile/keyboard",
            "1366/375/320 widths without page overflow; skip link and accessible table region",
        )

        page.evaluate("sessionStorage.setItem('saq-qa-token','qa-expired')")
        page.get_by_role("link", name="Объявления", exact=True).click()
        expect(
            page.get_by_role("heading", name="Доступ не подтверждён")
        ).to_be_visible()
        assert page.get_by_role("navigation").count() == 0
        page.get_by_role("button", name="Выйти", exact=True).click()
        login(page)
        checkpoint(
            "session loss",
            "API rejects previously accepted local token; workspace hidden, logout/sign-in restores access",
        )

        empty_ad = api(
            page,
            "POST",
            "/api/v1/advertisements",
            {
                "complexId": "demo-complex-08",
                "platform": "DEMO LOCAL",
                "account": "qa-empty",
                "sourceUrl": "https://demo.invalid/qa-empty",
                "text": "DEMO: Бесплатная консультация, платежей нет.",
                "publishedAt": "2026-10-15T10:00:00Z",
            },
        )
        page.goto(BASE + "/complexes/demo-complex-08?tab=ads")
        empty_card = page.locator("article.advertisement-card").filter(
            has_text="qa-empty"
        )
        empty_card.get_by_role("button", name="Скриншоты и AI-анализ").click()
        empty_panel = empty_card.get_by_role("region", name="Анализ объявления")
        empty_panel.get_by_role(
            "button", name="Анализировать выбранный источник"
        ).click()
        empty_panel.get_by_text(re.compile("Анализ завершён")).click()
        expect(
            empty_panel.get_by_text(
                "Поддержанных гипотез нет. Это не подтверждение безопасности объекта."
            )
        ).to_be_visible()
        assert (
            api(page, "GET", f"/api/v1/advertisements/{empty_ad['id']}/hypotheses")[
                "items"
            ]
            == []
        )
        page.route(
            "**/api/v1/complexes/*/history?*",
            lambda route: route.fulfill(json={"items": [], "nextCursor": None}),
        )
        page.get_by_role("tab", name="История", exact=True).click()
        expect(
            page.get_by_role("heading", name="Действий аналитиков пока нет")
        ).to_be_visible()
        checkpoint(
            "empty results",
            "Harmless text has no hypotheses; no safety finding; explicit empty complex-history fixture",
        )

        assert not errors, errors
        assert not unexpected, unexpected
        checkpoint(
            "isolation",
            f"{len(requests)} browser requests; no page errors or external requests; no live Firebase/Gemini",
        )
    except Exception:
        page.screenshot(path=str(OUT / "failure.png"), full_page=True)
        (OUT / "failure.txt").write_text(page.locator("body").inner_text())
        raise
    finally:
        context.close()
        browser.close()
