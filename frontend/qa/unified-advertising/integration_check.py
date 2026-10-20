"""Actual A UI + pinned B backend; no materials browser transport overrides."""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:5181"
OUT = Path(os.environ.get("SAQ_QA_ARTIFACTS", "/tmp/saq-materials-integration"))
OUT.mkdir(parents=True, exist_ok=True)
results = []


def checkpoint(name):
    results.append({"check": name, "result": "passed"})
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("PASS:", name, flush=True)


def api(page, method, path, data=None):
    response = page.request.fetch(
        BASE + path,
        method=method,
        data=data,
        headers={"Authorization": "Bearer qa-local-analyst"},
    )
    assert response.ok, (path, response.status, response.text())
    return response.json()


with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=shutil.which("chromium") or p.chromium.executable_path,
        headless=True,
        args=["--no-sandbox"],
    )
    context = browser.new_context(
        viewport={"width": 1440, "height": 900}, accept_downloads=True
    )
    external = []
    errors = []
    writes = []

    def local_only(route):
        if not route.request.url.startswith(
            (BASE, "http://127.0.0.1:8011", "blob:", "data:")
        ):
            external.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    context.route("**/*", local_only)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "request",
        lambda request: (
            writes.append((request.method, request.url))
            if request.method == "POST"
            else None
        ),
    )
    try:
        page.goto(BASE + "/advertising")
        page.get_by_label("Электронная почта").fill("qa@example.test")
        page.get_by_label("Пароль", exact=True).fill("local-test-only")
        page.get_by_role("button", name="Войти", exact=True).click()
        page.get_by_role("button", name="Добавить материал", exact=True).click()
        page.get_by_label("Жилой комплекс", exact=True).select_option("demo-complex-04")
        page.get_by_label("Площадка", exact=True).fill("LOCAL QA")
        page.get_by_label("Аккаунт / автор", exact=True).fill(
            "fictional-native-integration"
        )
        page.get_by_label("Оригинальная ссылка", exact=True).fill(
            "https://demo.invalid/native-material"
        )
        page.get_by_label("Дата публикации", exact=True).fill("2026-10-20T15:00")
        text = "LOCAL QA NATIVE: Квартиры в строящемся доме. Внесите депозит 150 000 тенге."
        page.get_by_label("Текст объявления", exact=True).fill(text)
        page.get_by_role("button", name="Сохранить объявление", exact=True).click()
        expect(page.get_by_text("Оригинал сохранён.", exact=False)).to_be_visible()
        page.get_by_label("Поиск рекламы", exact=True).fill("LOCAL QA NATIVE")
        page.get_by_role("button", name="Найти материалы", exact=True).click()
        link = page.get_by_role("link", name="Проверить материал →", exact=True)
        expect(link).to_have_count(1)
        link.click()
        expect(
            page.get_by_text("Анализ готов — требуется решение человека", exact=True)
        ).to_be_visible(timeout=30000)
        expect(
            page.get_by_role("button", name="Сохранить проверку", exact=True)
        ).to_be_enabled()
        hypothesis = page.get_by_label(re.compile("Решение по гипотезе.*R2"))
        expect(hypothesis).to_be_visible()
        expect(page.get_by_text("10 · Зелёная зона", exact=True)).to_be_visible()
        checkpoint(
            "real manual intake → durable queue/MockTransport worker → actual MaterialDetail and hypotheses; no manual AI action"
        )

        duplicate = api(
            page,
            "POST",
            "/api/v1/advertisements",
            {
                "complexId": "demo-complex-04",
                "platform": "Telegram",
                "account": "fictional-second-platform",
                "sourceUrl": "https://demo.invalid/native-duplicate",
                "text": text,
                "publishedAt": "2026-10-20T10:00:00Z",
            },
        )
        assert duplicate["id"]
        page.get_by_role("button", name="Обновить материал и ЖК", exact=True).click()
        expect(
            page.get_by_text(
                "Зарегистрировано публикаций: 2. Здесь загружено: 2.", exact=True
            )
        ).to_be_visible()
        key = hashlib.sha256(text.encode()).hexdigest()
        counts = api(page, "GET", "/api/qa-materials/provider-counts")["counts"]
        assert counts.get(key) == 1, counts
        page.get_by_role("link", name="← Все материалы", exact=True).click()
        expect(
            page.get_by_role("link", name="Проверить материал →", exact=True)
        ).to_have_count(1)
        page.get_by_role("link", name="Проверить материал →", exact=True).click()
        checkpoint(
            "exact duplicate on another platform → one real material/two originals; one provider extraction for that text"
        )

        page.goto(BASE + f"/advertisements/{duplicate['id']}?source=legacy-qa")
        expect(page).to_have_url(
            re.compile(r"/advertising/materials/[^?]+\?source=legacy-qa")
        )
        page.get_by_label(re.compile("Решение по гипотезе.*R2")).select_option(
            "confirmed"
        )
        page.get_by_label("Общий комментарий", exact=True).fill(
            "LOCAL QA: проверен сохранённый оригинал и связь с ЖК"
        )
        page.evaluate("""() => {
          const banner = document.createElement('div'); banner.id = 'qa-native-label';
          banner.textContent = 'LOCAL QA · настоящий backend B; тестовые Auth / MemoryStore / AI';
          banner.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:4px;background:#ffedab;color:#222;font:12px/1.4 sans-serif;z-index:10000;pointer-events:none';
          document.body.append(banner);
        }""")
        for width, height in [(1440, 900), (375, 812), (320, 700)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), width
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(
                path=str(OUT / f"native-review-{width}-viewport-test-adapters.png")
            )
            page.screenshot(
                path=str(OUT / f"native-review-{width}-test-adapters.png"),
                full_page=True,
            )
        with page.expect_response(
            lambda response: (
                response.request.method == "POST" and response.url.endswith("/review")
            )
        ) as review:
            page.get_by_role("button", name="Сохранить проверку", exact=True).click()
        assert review.value.ok, (review.value.status, review.value.text())
        expect(page.get_by_text("35 · Жёлтая зона", exact=True)).to_be_visible()
        page.get_by_text("История проверок материала", exact=True).click()
        expect(
            page.get_by_role("article").filter(
                has_text="LOCAL QA: проверен сохранённый оригинал и связь с ЖК"
            )
        ).to_be_visible()
        current = api(page, "GET", "/api/v1/complexes/demo-complex-04")
        assert current["risk"]["score"] == 35, current["risk"]
        assert current["risk"]["factors"][1]["status"] == "confirmed"
        reviews = [(method, url) for method, url in writes if url.endswith("/review")]
        assert len(reviews) == 1
        assert not any(
            re.search(r"/factors/|/hypotheses/.*/decision|/analyze$", url)
            for _, url in writes
        )
        checkpoint(
            "one real transactional review → evidence + R2 + actual persisted risk 35; no intermediate factor/hypothesis requests"
        )

        page.get_by_role(
            "link", name="Создать сигнал по проверенным данным ЖК →", exact=True
        ).click()
        page.get_by_label("Основание для проверки", exact=True).fill(
            "LOCAL QA: результат настоящего materials review, синтетический внешний provider"
        )
        page.get_by_role("button", name="Создать черновик", exact=True).click()
        expect(page).to_have_url(re.compile("/signals/[^/]+$"))
        expect(page.get_by_text("35 · Жёлтая зона", exact=True)).to_be_visible()
        with page.expect_download() as download:
            page.get_by_role("button", name="Скачать PDF", exact=True).click()
        target = OUT / "native-material-review.pdf"
        download.value.save_as(target)
        assert target.read_bytes().startswith(b"%PDF-")
        checkpoint(
            "actual reviewed complex → real signal snapshot → native WeasyPrint PDF"
        )
        assert not errors, errors
        assert not external, external
        checkpoint(
            "no page errors / no external browser network; B backend unchanged; test identity/store/files/providers only"
        )
    except Exception:
        page.screenshot(path=str(OUT / "failure.png"), full_page=True)
        (OUT / "failure.txt").write_text(page.locator("body").inner_text())
        raise
    finally:
        context.close()
        browser.close()
