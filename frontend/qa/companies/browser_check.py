"""Company workflow against explicit localhost-only QA adapters; no live sources."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:5182"
OUT = Path(os.environ.get("SAQ_QA_ARTIFACTS", "/tmp/saq-company-browser"))
OUT.mkdir(parents=True, exist_ok=True)


def main():
    errors, external = [], []
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
        page.goto(BASE + "/companies")
        page.get_by_label("Электронная почта").fill("qa@example.test")
        page.get_by_label("Пароль", exact=True).fill("local-test-only")
        page.get_by_role("button", name="Войти", exact=True).click()
        expect(
            page.get_by_role("heading", name="Организации", exact=True)
        ).to_be_visible()
        page.get_by_label("Название ЖК или адрес").fill("Учебный берег")
        page.get_by_role("button", name="Найти в Homeportal").click()
        page.get_by_role("button", name="Посмотреть участников").click()
        expect(page.get_by_text("Юридический застройщик", exact=True)).to_be_visible()
        expect(page.get_by_text("Уполномоченная компания", exact=True)).to_be_visible()
        page.get_by_role("checkbox").check()
        page.get_by_role("button", name="Сохранить участников").click()
        page.get_by_role("link", name="Открыть ЖК →").click()
        participants = page.get_by_role("region", name="Участники проекта")
        expect(participants.get_by_text("БИН 000000000001")).to_be_visible()
        expect(participants.get_by_text("БИН 000000000002")).to_be_visible()
        participants.get_by_role("link", name="Homeportal", exact=False).first.click(
            trial=True
        )
        participants.get_by_role("link", name="→").first.click()
        expect(page.get_by_role("heading", name="Основные сведения")).to_be_visible()
        expect(page.get_by_text("2010-02-01", exact=True)).to_be_visible()
        expect(page.get_by_text("Сведения пока не найдены").first).to_be_visible()
        adata = page.get_by_role("link", name="ADATA", exact=False)
        expect(adata).to_have_attribute(
            "href", "https://pk.adata.kz/company/000000000001"
        )
        expect(adata).to_have_attribute("title", __import__("re").compile("Получено"))
        page.get_by_role("button", name="Обновить по источникам").click()
        expect(
            page.get_by_role("button", name="Обновить по источникам")
        ).to_be_enabled()
        page.reload()
        expect(page.get_by_text("2010-02-01", exact=True)).to_be_visible()
        page.screenshot(path=str(OUT / "company-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.get_by_role("heading", name="Основные сведения")).to_be_visible()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), "Mobile overflow"
        page.screenshot(path=str(OUT / "company-mobile.png"), full_page=True)
        # Protected direct URL still needs the test identity header through the app.
        assert page.request.get(BASE + "/api/v1/companies").status == 401
        assert not errors and not external, {
            "pageErrors": errors,
            "externalRequests": external,
        }
        (OUT / "results.json").write_text(
            json.dumps(
                {
                    "result": "passed",
                    "workflow": [
                        "authenticated search",
                        "two-role preview",
                        "explicit real-scope synthetic import",
                        "complex role links",
                        "BIN-matched registration citation",
                        "refresh and deep reload",
                        "mobile no overflow",
                        "unauthenticated API denied",
                        "no external browser requests",
                    ],
                    "pageErrors": errors,
                    "externalRequests": external,
                },
                indent=2,
            )
        )
        browser.close()
        print(
            "PASS: company workflow, two roles, citations, refresh, direct URL, mobile and auth"
        )


if __name__ == "__main__":
    main()
