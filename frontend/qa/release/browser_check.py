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
        # A fresh module cache is necessary: the full workflow below visits all
        # routes and cannot reproduce a first lazy-import failure afterwards.
        chunk_context = browser.new_context()
        chunk_context.route("**/*", local_only)
        chunk_page = chunk_context.new_page()
        chunk_page.on("pageerror", lambda e: errors.append(str(e)))
        chunk_requests = []
        chunk_page.on("request", lambda r: chunk_requests.append((r.method, r.url)))
        chunk_pattern = "**/src/features/signals/SignalsPage.tsx*"
        chunk_page.route(chunk_pattern, lambda route: route.abort())
        try:
            chunk_page.goto(BASE + "/signals")
            expect(
                chunk_page.get_by_role("button", name="Войти", exact=True)
            ).to_be_visible()
            assert not any("/features/signals/" in url for _, url in chunk_requests)
            login(chunk_page)
            expect(chunk_page.get_by_role("alert")).to_contain_text(
                "Не удалось загрузить раздел"
            )
            held_chunks = []
            list_pattern = "**/src/features/complexes/ComplexList.tsx*"
            chunk_page.route(list_pattern, lambda route: held_chunks.append(route))
            with chunk_page.expect_request(list_pattern):
                chunk_page.get_by_role("link", name="Реестр ЖК", exact=True).click()
            expect(chunk_page.get_by_role("status")).to_contain_text("Загружаем данные")
            expect(chunk_page.get_by_role("navigation")).to_be_visible()
            assert held_chunks, "Complex list import was not held"
            chunk_page.unroute(list_pattern)
            for held_chunk in held_chunks:
                held_chunk.continue_()
            expect(chunk_page.get_by_label("Поиск ЖК")).to_be_visible()
            expect(chunk_page.locator("#main-content")).to_be_focused()
            chunk_page.get_by_role("link", name="Сигналы", exact=True).click()
            expect(chunk_page.get_by_role("alert")).to_contain_text(
                "Не удалось загрузить раздел"
            )
            chunk_page.unroute(chunk_pattern)
            chunk_page.get_by_role("button", name="Перезагрузить страницу").click()
            expect(
                chunk_page.get_by_role("heading", name="Сигналы", exact=True)
            ).to_be_visible()
            assert not any(method == "POST" for method, _ in chunk_requests)
            checkpoint(
                "lazy route recovery",
                "Protected route is not fetched before login; failed import keeps navigation; pending import shows loading; another route and focus work; same-URL reload recovers without replaying writes",
            )
        finally:
            chunk_context.close()

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
        expect(page).not_to_have_url(re.compile(r"(?:\?|&)q="))
        expect(page.get_by_role("region", name="Жилые комплексы")).to_be_visible()
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
        expect(page.get_by_role("region", name="Жилые комплексы")).to_be_visible()
        # Let intercepted route.fetch requests finish before removing their handlers.
        page.wait_for_load_state("networkidle")
        page.unroute_all(behavior="wait")
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
        error_once(
            page,
            "**/api/v1/evidence/*/file",
            200,
            body="<html>TEST gateway response</html>",
            content_type="text/html",
        )
        panel.get_by_role("button", name="Открыть скриншот").click()
        expect(panel.get_by_role("alert")).to_contain_text(
            "Сервер не вернул изображение"
        )
        error_once(
            page,
            "**/api/v1/evidence/*/file",
            200,
            body="TEST invalid PNG bytes",
            content_type="image/png",
        )
        panel.get_by_role("button", name="Открыть скриншот").click()
        expect(panel.get_by_role("alert")).to_contain_text(
            "Не удалось отобразить скриншот"
        )
        panel.get_by_role("button", name="Открыть скриншот").click()
        expect(panel.get_by_role("img")).to_be_visible()
        page.wait_for_function(
            "document.querySelector('.analysis-panel img')?.naturalWidth > 0"
        )
        selected_image = panel.get_by_label("Источник анализа").input_value()
        card.get_by_role("button", name="Скрыть анализ").click()
        expect(panel).to_be_hidden()
        card.get_by_role("button", name="Скриншоты и AI-анализ").click()
        expect(panel.get_by_label("Источник анализа")).to_have_value(selected_image)
        expect(panel.get_by_role("img")).to_be_visible()
        expect(panel.locator(".selected-source")).to_contain_text("Скриншот 1")
        expect(panel.get_by_text("Загружен файл", exact=False)).to_contain_text(
            "synthetic.png"
        )
        for width, height in [(1366, 768), (375, 812), (320, 700)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), width
        page.set_viewport_size({"width": 1366, "height": 768})
        panel.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "desktop-analysis.png"), full_page=True)
        page.set_viewport_size({"width": 375, "height": 812})
        page.screenshot(path=str(OUT / "mobile-analysis.png"), full_page=True)
        page.set_viewport_size({"width": 1366, "height": 768})
        assert (
            panel.locator("blockquote").first.evaluate(
                "el => parseFloat(getComputedStyle(el).fontSize)"
            )
            >= 16
        )
        source_select = panel.get_by_label("Источник анализа")
        source_select.focus()
        page.keyboard.press("Space")
        if page.evaluate("CSS.supports('appearance', 'base-select')"):
            page.wait_for_function(
                "document.querySelector('.analysis-panel select').matches(':open')"
            )
            page.wait_for_timeout(200)  # Capture the finished 160 ms picker transition.
        page.screenshot(path=str(OUT / "source-dropdown.png"))
        page.keyboard.press("Escape")
        page.emulate_media(reduced_motion="reduce")
        assert panel.evaluate("el => getComputedStyle(el).animationName") == "none"
        page.emulate_media(reduced_motion="no-preference")
        panel.get_by_label("Источник анализа").select_option("")
        expect(panel.locator(".selected-source")).to_contain_text("Текст объявления")
        checkpoint(
            "screenshots",
            "Wrong MIME, >6 MiB rejected; corrupt PNG rejected; valid PNG stored/read with private local API",
        )

        panel.get_by_role("button", name="Рассмотреть гипотезу").click()
        panel.get_by_label("Обоснование", exact=True).fill(
            "LOCAL TEST: принять только к проверке источника"
        )
        card.get_by_role("button", name="Скрыть анализ").click()
        card.get_by_role("button", name="Скриншоты и AI-анализ").click()
        expect(panel.get_by_label("Обоснование", exact=True)).to_have_value(
            "LOCAL TEST: принять только к проверке источника"
        )
        hypothesis = api(page, "GET", f"/api/v1/advertisements/{ad['id']}/hypotheses")[
            "items"
        ][0]
        api(
            page,
            "POST",
            f"/api/v1/hypotheses/{hypothesis['id']}/decision",
            {
                "decision": "accepted",
                "expectedVersion": hypothesis["version"],
                "notes": "LOCAL TEST: concurrent hypothesis review",
            },
        )
        panel.get_by_role("button", name="Сохранить решение", exact=True).click()
        expect(panel.get_by_role("alert")).to_contain_text("Данные изменились")
        panel.get_by_role("button", name="Обновить результаты").click()
        expect(
            panel.get_by_text(re.compile("Несохранённый текст вашего решения"))
        ).to_contain_text("LOCAL TEST: принять только к проверке источника")
        expect(
            panel.get_by_text("Принято для проверки доказательства", exact=True)
        ).to_be_visible()
        assert api(page, "GET", "/api/v1/complexes/demo-complex-04/risk")["score"] == 10
        panel.get_by_role("link", name="К доказательству").click()
        page.reload()
        expect(page.get_by_text("Источник, выбранный по ссылке")).to_be_focused()
        page.set_viewport_size({"width": 375, "height": 812})
        evidence = page.locator("article.evidence-card").filter(has_text="135 000")
        evidence.get_by_role("button", name="Проверить источник", exact=True).click()
        evidence.get_by_label(
            "Источник содержит прямое предложение внести платёж"
        ).check()
        evidence.get_by_label("Обоснование решения").fill(
            "LOCAL TEST: сверено с точным оригиналом"
        )
        api(
            page,
            "POST",
            f"/api/v1/evidence/{hypothesis['evidenceId']}/decision",
            {
                "decision": "rejected",
                "expectedVersion": 1,
                "notes": "LOCAL TEST concurrent source reviewer",
            },
        )
        evidence.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(evidence.get_by_role("alert")).to_contain_text("Данные изменились")
        evidence.get_by_role("button", name="Обновить источник", exact=True).focus()
        page.keyboard.press("Enter")
        expect(
            evidence.get_by_text(re.compile("Актуальная версия источника: 2"))
        ).to_be_visible()
        expect(evidence.get_by_label("Обоснование решения")).to_have_value(
            "LOCAL TEST: сверено с точным оригиналом"
        )
        expect(
            evidence.get_by_label("Источник содержит прямое предложение внести платёж")
        ).to_be_checked()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
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
        mutate_complex(page)
        risk.get_by_role("button", name="Сохранить решение", exact=True).click()
        expect(risk.get_by_role("alert")).to_contain_text("Данные изменились")
        risk.get_by_role("button", name="Обновить данные ЖК").click()
        expect(risk.get_by_text(re.compile("Актуальная версия ЖК"))).to_be_visible()
        expect(risk.get_by_label("Обоснование", exact=True)).to_have_value(
            "LOCAL TEST: отдельное подтверждение R2"
        )
        expect(risk.get_by_role("checkbox", name=re.compile("135 000"))).to_be_checked()
        risk.get_by_role("button", name="Сохранить решение", exact=True).click()
        expect(risk.locator(".risk-total")).to_contain_text("35")
        checkpoint(
            "human review separation",
            "AI acceptance 10 → source review 10 → explicit R2 35; backend calculates risk",
        )

        page.get_by_role("tab", name="Документы", exact=True).click()
        page.get_by_role("button", name="Пересмотреть", exact=True).click()
        page.get_by_label("Реквизиты", exact=True).fill("LOCAL TEST reference retained")
        page.get_by_label("Источник проверки", exact=True).fill(
            "LOCAL TEST source retained"
        )
        mutate_complex(page)
        page.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Данные изменились")
        page.get_by_role("button", name="Обновить данные ЖК").click()
        expect(page.get_by_label("Реквизиты", exact=True)).to_have_value(
            "LOCAL TEST reference retained"
        )
        expect(page.get_by_label("Источник проверки", exact=True)).to_have_value(
            "LOCAL TEST source retained"
        )
        page.get_by_role("button", name="Сохранить проверку", exact=True).click()
        expect(
            page.get_by_role("button", name="Пересмотреть", exact=True)
        ).to_be_visible()
        checkpoint(
            "editor conflicts",
            "Real concurrent AI/source/factor/basis decisions; explicit GET refresh; notes and selections retained at 375px, keyboard retry",
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
        error_once(
            page,
            "**/api/v1/signals/*/report",
            200,
            body="<html>TEST mislabeled gateway error</html>",
            content_type="application/pdf",
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
        empty_panel.locator(".analysis-history > summary").click()
        empty_panel.locator(".analysis-history").get_by_text(
            re.compile("Анализ завершён")
        ).click()
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

        # LINK-05: real local routes/services, synthetic accounts; no AI request.
        # Let intercepted route.fetch requests finish before removing their handlers.
        page.wait_for_load_state("networkidle")
        page.unroute_all(behavior="wait")
        page.set_viewport_size({"width": 1366, "height": 768})
        trace_ads = []
        texts = [
            "DEMO TRACE: контакт +7 (000) 000-00-01.",
            "DEMO TRACE: WhatsApp https://wa.me/70000000001",
            "DEMO TRACE: 8 (000) 000-00-01.",
        ]
        for index, text in enumerate(texts):
            trace_ads.append(
                api(
                    page,
                    "POST",
                    "/api/v1/advertisements",
                    {
                        "complexId": "demo-complex-04",
                        "platform": "DEMO TRACE",
                        "account": f"fictional-trace-{index}",
                        "sourceUrl": f"https://demo.invalid/trace/{index}",
                        "text": text,
                        "publishedAt": "2026-10-16T10:00:00Z",
                    },
                )
            )
        trace_risk = api(page, "GET", "/api/v1/complexes/demo-complex-04/risk")
        ai_before = len(
            [r for r in requests if r[0] == "POST" and r[1].endswith("/analyze")]
        )
        page.goto(BASE + f"/advertisements/{trace_ads[0]['id']}")
        expect(page.locator(".ad-text")).to_have_text(texts[0])
        page.get_by_role("button", name="Рекламный след", exact=True).click()
        trace = page.get_by_role("region", name="Рекламный след", exact=True)
        other = trace.locator(".trace-card").filter(has_text="fictional-trace-1")
        expect(other.get_by_text("+7 (000) 000-00-01", exact=True)).to_be_visible()
        expect(
            other.get_by_text("https://wa.me/70000000001", exact=True)
        ).to_be_visible()
        for width, height in [(1366, 768), (375, 812), (320, 700)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), width
        page.set_viewport_size({"width": 1366, "height": 768})
        other.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "advertising-trace-desktop.png"))
        other.get_by_role("button", name="Рассмотреть совпадение").click()
        other.get_by_label("Обоснование совпадения").fill(
            "LOCAL DEMO: сверены телефон и WhatsApp"
        )
        page.get_by_role("button", name="Скрыть рекламный след", exact=True).click()
        page.get_by_role("button", name="Рекламный след", exact=True).click()
        expect(other.get_by_label("Обоснование совпадения")).to_have_value(
            "LOCAL DEMO: сверены телефон и WhatsApp"
        )
        other.get_by_role("button", name="Отмена", exact=True).click()
        trigger = other.get_by_role("button", name="Рассмотреть совпадение")
        expect(trigger).to_be_focused()
        expect(trigger).to_have_attribute("aria-expanded", "false")
        page.keyboard.press("Enter")
        other.get_by_label("Обоснование совпадения").fill(
            "LOCAL DEMO: сверены телефон и WhatsApp"
        )
        other.get_by_role("button", name="Сохранить решение о совпадении").click()
        expect(other.get_by_text("Совпадение подтверждено", exact=True)).to_be_visible()
        page.reload()
        page.get_by_role("button", name="Рекламный след", exact=True).click()
        other = page.locator(".trace-card").filter(has_text="fictional-trace-1")
        expect(other.get_by_text("Совпадение подтверждено", exact=True)).to_be_visible()
        other.get_by_role("link", name="К связанному объявлению").click()
        expect(page).to_have_url(BASE + f"/advertisements/{trace_ads[1]['id']}")
        expect(page.locator(".ad-text")).to_have_text(texts[1])
        page.goto(BASE + f"/advertisements/{trace_ads[0]['id']}")
        page.get_by_role("button", name="Рекламный след", exact=True).click()
        rejected = page.locator(".trace-card").filter(has_text="fictional-trace-2")
        rejected.get_by_role("button", name="Рассмотреть совпадение").click()
        rejected.get_by_label("Решение по совпадению").select_option("rejected")
        rejected.get_by_label("Обоснование совпадения").fill(
            "LOCAL DEMO: учебное отклонение"
        )
        error_once(page, "**/api/v1/ad-links/*/decision", 409, "CONFLICT")
        rejected.get_by_role("button", name="Сохранить решение о совпадении").click()
        expect(page.get_by_role("alert")).to_contain_text("Данные изменились")
        page.get_by_role("button", name="Обновить совпадения").click()
        expect(rejected.get_by_label("Обоснование совпадения")).to_have_value(
            "LOCAL DEMO: учебное отклонение"
        )
        expect(rejected.get_by_label("Решение по совпадению")).to_have_value("rejected")
        rejected.get_by_role("button", name="Сохранить решение о совпадении").click()
        expect(rejected.get_by_text("Совпадение отклонено", exact=True)).to_be_visible()
        assert api(page, "GET", "/api/v1/complexes/demo-complex-04/risk") == trace_risk
        assert (
            len([r for r in requests if r[0] == "POST" and r[1].endswith("/analyze")])
            == ai_before
        )
        page.set_viewport_size({"width": 375, "height": 812})
        page.screenshot(path=str(OUT / "advertising-trace-mobile.png"), full_page=True)
        checkpoint(
            "advertising trace",
            "Exact phone/WhatsApp quotes; explicit confirm/reject and persisted reload; direct ad navigation; conflict keeps notes; 1366/375/320 without overflow; no AI or risk mutation",
        )

        # MON uses only the explicit MockTransport adapter in local_api.py.
        # No live social API, real ads, paid Gemini or Scheduler is touched.
        page.set_viewport_size({"width": 1366, "height": 900})
        page.goto(BASE + "/monitoring")
        expect(page.get_by_role("heading", name="Мониторинг рекламы", exact=True)).to_be_visible()
        expect(page.get_by_role("heading", name="Источник Instagram настроен через SearchAPI")).to_be_visible()
        expect(page.get_by_text("Ещё не подтверждён. Ручной сбор доступен в источниках.")).to_be_visible()
        page.get_by_role("button", name="Источники сбора", exact=True).click()
        expect(page.get_by_role("checkbox")).not_to_be_checked()
        page.get_by_role("button", name="Сохранить источник", exact=True).click()
        expect(page.get_by_text("Источник сохранён. Он доступен для регулярного сбора.")).to_be_visible()
        page.get_by_role("button", name="Получить публикации", exact=True).click()
        expect(page.get_by_text("Сбор завершён: прочитано 1, подходит под фильтр 1, новых 1, повторов 0")).to_be_visible()
        page.get_by_role("button", name="Очередь эксперта", exact=True).click()
        page.get_by_role("button", name="Рассмотреть находку", exact=True).click()
        detail = page.locator(".monitor-detail")
        expect(detail.get_by_text("Поисковый фрагмент — требуется оригинал", exact=True)).to_be_visible()
        expect(detail.get_by_text("Опубликовано: Не указано", exact=False)).to_be_visible()
        note = "LOCAL QA: проверить оригинал и основание; не юридическое заключение"
        detail.get_by_label("Обоснование решения").fill(note)
        item_id = page.url.split("item=")[1].split("&")[0]
        api(page, "POST", f"/api/v1/monitoring/items/{item_id}/review", {
            "expectedVersion": 1, "decision": "investigating", "notes": "LOCAL QA: concurrent review",
        })
        detail.get_by_role("button", name="Сохранить решение эксперта", exact=True).click()
        expect(detail.get_by_role("alert")).to_contain_text("Данные изменились")
        detail.get_by_role("button", name="Обновить материал", exact=True).click()
        expect(detail.get_by_label("Обоснование решения")).to_have_value(note)
        detail.get_by_role("button", name="Сохранить решение эксперта", exact=True).click()
        expect(detail.get_by_text("Решение по находке сохранено. Оценка R1–R6 не менялась.")).to_be_visible()
        detail.get_by_role("button", name="Анализировать Gemini — платный запрос", exact=True).click()
        expect(detail.get_by_text("Попытка анализа завершена. Проверьте результат и статус ниже.")).to_be_visible()
        expect(detail.get_by_text("R2 · Предложение внести платёж", exact=True)).to_be_visible()
        expect(detail.get_by_text("Реальную публикацию нельзя приписывать", exact=False)).to_be_visible()
        for width in [1366, 375, 320]:
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        page.screenshot(path=str(OUT / "monitoring-mobile-test-adapters.png"), full_page=True)
        page.set_viewport_size({"width": 1366, "height": 900})
        page.screenshot(path=str(OUT / "monitoring-desktop-test-adapters.png"), full_page=True)
        page.reload()
        expect(page.locator(".monitor-detail .inline-notice").filter(has_text=note)).to_be_visible()
        assert api(page, "GET", "/api/v1/complexes/demo-complex-04/risk") == trace_risk
        checkpoint("public monitoring", "Synthetic RSS → bounded collection → queue → real 409/refresh keeps notes → expert review → MockTransport Gemini → persisted reload; unknown dates/Instagram limitation/DEMO separation; 1366/375/320 without overflow; risk unchanged")


        # The QA process strips live SEARCHAPI_* and uses the explicit synthetic transport.
        page.get_by_role("button", name="Источники сбора", exact=True).click()
        page.get_by_label("Название источника", exact=True).fill("LOCAL QA Instagram source")
        page.get_by_label("Тип источника", exact=True).select_option("instagram_ads")
        expect(page.get_by_label("Поисковый запрос")).to_have_value("квартиры Өскемен")
        expect(page.get_by_text("Каждый запуск расходует запрос SearchAPI.", exact=False)).to_be_visible()
        page.get_by_role("button", name="Сохранить источник", exact=True).click()
        panel = page.locator(".monitor-sources > .panel").filter(has=page.get_by_role("heading", name="LOCAL QA Instagram source", exact=True))
        expect(panel.get_by_text("Только ручной сбор.", exact=False)).to_be_visible()
        panel.get_by_role("button", name="Получить публикации", exact=True).click()
        expect(page.get_by_text("Сбор завершён: прочитано 1, подходит под фильтр 1, новых 1, повторов 0")).to_be_visible()
        page.get_by_role("button", name="Очередь эксперта", exact=True).click()
        finding = page.locator(".monitor-finding").filter(has=page.get_by_role("heading", name="LOCAL QA DEMO Instagram", exact=True))
        finding.get_by_role("button", name="Рассмотреть находку").click()
        detail = page.locator(".monitor-detail")
        expect(detail.get_by_text("Instagram · Meta Ad Library", exact=True)).to_be_visible()
        expect(detail.get_by_text("ID 100000000000099", exact=False)).to_be_visible()
        expect(detail.get_by_text("Опубликовано: Не указано", exact=False)).to_be_visible()
        expect(detail.get_by_text("Это не дата публикации исходного поста.", exact=False)).to_be_visible()
        detail.locator("summary").filter(has_text="Рекламные материалы").click()
        expect(detail.get_by_role("link", name="Видео 1")).to_have_attribute("href", "https://media.example.org/qa-demo.mp4")
        assert detail.locator("img,video,iframe").count() == 0
        for width in [1366, 375, 320]:
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        page.screenshot(path=str(OUT / "instagram-mobile-test-adapters.png"), full_page=True)
        page.set_viewport_size({"width": 1366, "height": 900})
        page.screenshot(path=str(OUT / "instagram-desktop-test-adapters.png"), full_page=True)
        page.get_by_role("button", name="Источники сбора", exact=True).click()
        page.get_by_label("Название источника", exact=True).fill("LOCAL QA reserve safeguard")
        page.get_by_label("Тип источника", exact=True).select_option("instagram_ads")
        page.get_by_label("Поисковый запрос").fill("квартиры Риддер")
        page.get_by_role("button", name="Сохранить источник", exact=True).click()
        reserve_panel = page.locator(".monitor-sources > .panel").filter(has=page.get_by_role("heading", name="LOCAL QA reserve safeguard", exact=True))
        reserve_panel.get_by_role("button", name="Получить публикации", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="сохраняем минимум 20 запросов")).to_be_visible()
        state = api(page, "GET", "/api/v1/monitoring/status")
        assert state["searchApi"]["dailyUsed"] == 2 and state["searchApi"]["unsettledAttempts"] == 0
        assert api(page, "GET", "/api/v1/complexes/demo-complex-04/risk") == trace_risk
        checkpoint("Instagram Ad Library", "Synthetic Meta engine → Instagram source → provenance/campaign date/media links → no auto media requests → reserve stops before second search; 1366/375/320; risk unchanged")
        page.goto(BASE + f"/advertisements/{empty_ad['id']}")
        page.get_by_role("button", name="Скриншоты и AI-анализ").click()
        image_panel = page.get_by_role("region", name="Анализ объявления")
        image_panel.get_by_label("Добавить скриншот").set_input_files(
            {
                "name": "synthetic-image-path.png",
                "mimeType": "image/png",
                "buffer": image.getvalue(),
            }
        )
        image_panel.get_by_role("button", name="Загрузить", exact=True).click()
        expect(image_panel.get_by_label("Источник анализа")).not_to_have_value("")
        selected = image_panel.get_by_label("Источник анализа").input_value()
        with page.expect_request(
            lambda request: (
                request.url.endswith("/analyze") and request.method == "POST"
            )
        ) as image_request:
            image_panel.get_by_role(
                "button", name="Анализировать выбранный источник"
            ).click()
        payload = image_request.value.post_data_json
        assert payload["screenshotId"] == selected
        assert payload["expectedVersion"] == 2
        expect(
            image_panel.get_by_role("button", name="Анализировать выбранный источник")
        ).to_be_enabled()
        run = api(page, "GET", f"/api/v1/advertisements/{empty_ad['id']}/analysis")[
            "items"
        ]
        assert any(
            item["screenshotId"] == selected and item["status"] == "succeeded"
            for item in run
        )
        checkpoint(
            "A-01 recovery",
            "Image upload → auto-selection → image analysis via MockTransport; HTML/decode recovery; disclosures retain selection/drafts; trace cancel restores keyboard focus",
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
