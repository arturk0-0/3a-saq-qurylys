"""Local synthetic photo + explicit AI/identity/storage adapters; no external traffic."""

import io
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:5183"
OUT = Path(os.environ.get("SAQ_QA_ARTIFACTS", "/tmp/saq-drone-browser"))
OUT.mkdir(parents=True, exist_ok=True)


def fixture():
    image = Image.new("RGB", (1280, 720), "#e6eff3")
    draw = ImageDraw.Draw(image)
    draw.rectangle((400, 150, 850, 550), fill="#67828e")
    for x in range(180, 1100, 40):
        draw.line((x, 580, x, 640), fill="#335c52", width=5)
    draw.line((180, 580, 1100, 580), fill="#335c52", width=5)
    draw.text((30, 30), "LOCAL QA - SYNTHETIC IMAGE, NOT A DRONE PHOTO", fill="#102c37")
    data = io.BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def main():
    data = fixture()
    errors, external, analyses = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000})

        def guard(route):
            if urlsplit(route.request.url).hostname not in ("127.0.0.1", "localhost"):
                external.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        context.route("**/*", guard)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda r: (
                analyses.append(r.url)
                if r.method == "POST" and r.url.endswith("/analyze")
                else None
            ),
        )
        page.goto(BASE + "/drone-inspections")
        page.get_by_label("Электронная почта").fill("qa@example.test")
        page.get_by_label("Пароль", exact=True).fill("local-test-only")
        page.get_by_role("button", name="Войти", exact=True).click()
        expect(
            page.get_by_role("heading", name="Дрон-инспекция", exact=True)
        ).to_be_visible()
        page.get_by_label("Название инспекции").fill("LOCAL QA — северный ракурс")
        page.get_by_label("Жилой комплекс", exact=True).select_option("demo-complex-01")
        page.get_by_label("Пункт 1", exact=True).fill("Ограждение со стороны съёмки")
        page.get_by_role("button", name="Добавить пункт").click()
        page.get_by_label("Пункт 4", exact=True).fill("Видимость прохода на площадку")
        page.get_by_role("button", name="Удалить пункт 4").click()
        page.get_by_label("Фотография с дрона", exact=True).set_input_files(
            {"name": "local-qa.png", "mimeType": "image/png", "buffer": data}
        )
        headers = {"Authorization": "Bearer qa-local-analyst"}
        before = page.request.get(
            BASE + "/api/v1/complexes/demo-complex-01/risk", headers=headers
        ).json()
        page.get_by_role("button", name="Загрузить фотографию", exact=True).click()
        expect(
            page.get_by_role("heading", name="LOCAL QA — северный ракурс", exact=True)
        ).to_be_visible()
        expect(
            page.get_by_alt_text("Снимок: LOCAL QA — северный ракурс")
        ).to_be_visible()
        assert not analyses, "Uploading must not start AI"
        record_id = page.url.rsplit("/", 1)[1]
        photo_url = BASE + "/api/v1/drone-inspections/" + record_id + "/photo"
        assert page.request.get(photo_url).status == 401
        original = page.request.get(photo_url, headers=headers)
        assert (
            original.body() == data and original.headers["cache-control"] == "no-store"
        )
        page.get_by_role("button", name="Анализировать фотографию", exact=True).click()
        results = page.locator("section").filter(
            has=page.get_by_role("heading", name="Наблюдения ИИ", exact=True)
        )
        expect(results.get_by_text("Видно на снимке", exact=True)).to_be_visible()
        expect(results.get_by_text("Не видно в кадре", exact=True)).to_be_visible()
        expect(results.get_by_text("Нельзя определить", exact=True)).to_be_visible()
        expect(
            results.get_by_text("Ограждение со стороны съёмки", exact=True)
        ).to_be_visible()
        page.get_by_label("Комментарий эксперта").fill(
            "Проверить противоположную сторону площадки."
        )
        page.get_by_role("button", name="Сохранить решение", exact=True).click()
        expect(page.get_by_text("Рассмотрено экспертом", exact=True)).to_be_visible()
        page.get_by_label("Результат рассмотрения").select_option("accepted")
        page.get_by_label("Комментарий эксперта").fill(
            "Наблюдения рассмотрены, нужен дополнительный ракурс."
        )
        page.get_by_role("button", name="Сохранить решение", exact=True).click()
        history = page.locator("section").filter(
            has=page.get_by_role("heading", name="История решений", exact=True)
        )
        expect(history.locator("article")).to_have_count(2)
        assert "qa-local-analyst" not in page.locator("body").inner_text()
        page.get_by_role("button", name="Проанализировать заново", exact=True).click()
        expect(
            page.get_by_role("heading", name="Решение эксперта", exact=True)
        ).to_be_visible()
        expect(
            history.get_by_text("предыдущий анализ", exact=False).first
        ).to_be_visible()
        page.reload()
        expect(
            page.get_by_role("heading", name="LOCAL QA — северный ракурс", exact=True)
        ).to_be_visible()
        expect(
            page.get_by_alt_text("Снимок: LOCAL QA — северный ракурс")
        ).to_be_visible()
        assert len(analyses) == 2, "Reload/reading must not trigger AI"
        after = page.request.get(
            BASE + "/api/v1/complexes/demo-complex-01/risk", headers=headers
        ).json()
        assert before == after
        page.screenshot(path=str(OUT / "drone-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        expect(
            page.get_by_role("heading", name="Наблюдения ИИ", exact=True)
        ).to_be_visible()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), "Mobile overflow"
        page.screenshot(path=str(OUT / "drone-mobile.png"), full_page=True)
        assert not errors and not external, {"pageErrors": errors, "external": external}
        result = {
            "result": "passed",
            "groups": [
                "auth/deep route",
                "editable checklist",
                "private original upload/download",
                "explicit analysis only",
                "three observation states",
                "versioned expert decisions/history",
                "new-run isolation",
                "reload no AI",
                "unchanged risk",
                "desktop/mobile",
                "no external traffic/page errors",
            ],
            "pageErrors": errors,
            "externalRequests": external,
            "syntheticAiCalls": len(analyses),
        }
        (OUT / "results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        browser.close()
        print(
            "PASS: drone upload → visual observations → expert review/history → reload/mobile; risk unchanged"
        )


if __name__ == "__main__":
    main()
