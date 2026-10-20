"""Local-only map checks. Synthetic API edge cases and neutral tile fixtures."""

import copy
import io
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:5181"
OUT = Path(os.environ.get("SAQ_QA_ARTIFACTS", "/tmp/saq-city-map"))
OUT.mkdir(parents=True, exist_ok=True)
results = []


def checkpoint(name):
    results.append({"check": name, "result": "passed"})
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("PASS:", name, flush=True)


def login(page):
    page.get_by_label("Электронная почта").fill("qa@example.test")
    page.get_by_label("Пароль", exact=True).fill("local-test-only")
    page.get_by_role("button", name="Войти", exact=True).click()
    expect(page.get_by_role("navigation", name="Основная навигация")).to_be_visible()


tile = Image.new("RGB", (256, 256), "#eaf0ed")
draw = ImageDraw.Draw(tile)
for position in range(0, 256, 64):
    draw.line((position, 0, position, 256), fill="#ceddd5", width=2)
    draw.line((0, position, 256, position), fill="#ceddd5", width=2)
tile_bytes = io.BytesIO()
tile.save(tile_bytes, format="PNG")

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get("SAQ_CHROMIUM")
        or shutil.which("chromium")
        or p.chromium.executable_path,
        headless=True,
        args=["--no-sandbox"],
    )
    errors = []
    external = []

    def local_only(route):
        if urlsplit(route.request.url).hostname not in ["localhost", "127.0.0.1"]:
            external.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    context = browser.new_context(
        viewport={"width": 1366, "height": 768}, reduced_motion="reduce"
    )
    context.route("**/*", local_only)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    try:
        response = page.request.get(
            BASE + "/api/v1/complexes?limit=50",
            headers={"Authorization": "Bearer qa-local-analyst"},
        )
        assert response.ok
        source = response.json()["items"][0]
        records = []
        for index in range(1, 9):
            record = copy.deepcopy(source)
            record.update(
                id=f"demo-complex-{index:02}",
                name=f"DEMO — Учебный ЖК {index}",
                address=f"Условная улица, {index}",
                city="Усть-Каменогорск",
                stage="under_construction",
                demo=True,
                coordinates={"latitude": 49.95, "longitude": 82.61},
            )
            records.append(record)
        records[0]["name"] = "DEMO — <img src=x onerror=alert(1)>"
        records[2]["stage"] = "commissioned"
        records[3]["coordinates"] = {"latitude": 49.96, "longitude": 82.62}
        records[4]["coordinates"] = None
        records[5]["coordinates"] = {"latitude": 91, "longitude": 82}
        records[6]["city"] = "Риддер"
        records[7]["stage"] = "planning"
        fixture = {
            "items": records,
            "nextCursor": "50",
            "total": 120,
            "catalogLimited": True,
        }

        def catalog(route):
            route.fulfill(json=fixture)

        page.route("**/api/v1/complexes?*", catalog)
        page.route(
            "https://tile.openstreetmap.org/**",
            lambda route: route.fulfill(
                content_type="image/png", body=tile_bytes.getvalue()
            ),
        )
        page.goto(BASE + "/complexes")
        expect(page.get_by_role("button", name="Войти", exact=True)).to_be_visible()
        assert not any(
            "CityBuildingsMap" in url or "leaflet-src" in url for url in requests
        )
        login(page)
        expect(page.get_by_role("table")).to_be_visible()
        expect(
            page.get_by_role("button", name="Показать карту города")
        ).to_have_attribute("aria-expanded", "false")
        assert not any(
            "CityBuildingsMap" in url or "leaflet-src" in url for url in requests
        )
        checkpoint("protected registry; city map closed; no lazy map/Leaflet requests")

        page.get_by_role("button", name="Показать карту города").click()
        region = page.get_by_role(
            "region", name="Карта города с условными зданиями", exact=True
        )
        expect(region.locator(".leaflet-marker-icon")).to_have_count(2)
        expect(page.get_by_text("На карте: 3 из 5", exact=False)).to_be_visible()
        expect(
            page.get_by_text("Без корректных координат: 2", exact=False)
        ).to_be_visible()
        expect(page.get_by_text("DEMO: координаты", exact=False)).to_be_visible()
        expect(region.get_by_role("link", name="OpenStreetMap")).to_be_visible()
        icons = region.locator(".city-map-building svg")
        assert icons.nth(0).evaluate("node => node.outerHTML") == icons.nth(1).evaluate(
            "node => node.outerHTML"
        )
        checkpoint(
            "three identical volumetric models / two exact positions; city/stage/missing/coverage/DEMO/attribution"
        )

        shared = region.get_by_role("button", name="ЖК на этой точке: 2", exact=False)
        shared.focus()
        shared.press("Enter")
        expect(region.get_by_text(records[0]["name"], exact=True)).to_be_visible()
        assert (
            region.locator(".city-map-popup img, .city-map-popup script").count() == 0
        )
        expect(
            region.get_by_role(
                "link", name="Открыть карточку ЖК: " + records[1]["name"], exact=True
            )
        ).to_have_attribute("href", "/complexes/demo-complex-02")
        region.get_by_role(
            "link", name="Открыть карточку ЖК: " + records[0]["name"], exact=True
        ).click()
        expect(page).to_have_url(BASE + "/complexes/demo-complex-01")
        expect(
            page.get_by_role("heading", name="Янтарный берег", exact=True)
        ).to_be_visible()
        page.go_back()
        expect(page.get_by_role("button", name="Показать карту города")).to_be_visible()
        page.reload()
        expect(page.get_by_role("table")).to_be_visible()
        checkpoint(
            "keyboard marker; safe grouped popup; real local card navigation/back/reload"
        )

        page.get_by_role("button", name="Показать карту города").click()
        region = page.get_by_role(
            "region", name="Карта города с условными зданиями", exact=True
        )
        expect(region.locator(".leaflet-marker-icon")).to_have_count(2)
        before = len([url for url in requests if "/api/v1/complexes?" in url])
        page.get_by_label("Город на карте").select_option("Риддер")
        expect(region.locator(".leaflet-marker-icon")).to_have_count(1)
        assert len([url for url in requests if "/api/v1/complexes?" in url]) == before
        page.get_by_label("Город на карте").select_option("Усть-Каменогорск")
        expect(region.locator(".leaflet-marker-icon")).to_have_count(2)
        region.scroll_into_view_if_needed()
        area = region.bounding_box()
        assert area
        old_position = region.locator(".leaflet-map-pane").get_attribute("style")
        x = area["x"] + area["width"] * 0.8
        y = area["y"] + area["height"] * 0.6
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 40, y + 20, steps=6)
        page.mouse.up()
        expect(region.locator(".leaflet-map-pane")).not_to_have_attribute(
            "style", old_position
        )
        page.evaluate("""() => {
          const label = document.createElement('div');
          label.textContent = 'LOCAL QA · тестовые данные и подложка';
          label.style.cssText = 'position:fixed;top:4px;left:12px;max-width:calc(100vw - 24px);padding:4px;background:#ffedab;color:#222;font:12px/1.4 sans-serif;z-index:10000;pointer-events:none';
          document.body.append(label);
        }""")

        for width, height in [(1366, 768), (375, 812), (320, 700)]:
            page.set_viewport_size({"width": width, "height": height})
            region.scroll_into_view_if_needed()
            expect(region).to_be_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), width
            assert region.evaluate("node => node.clientHeight") in range(318, 362)
            assert region.locator(".leaflet-marker-icon").count() == 2
            page.wait_for_function("""() => {
              const map = document.querySelector('.city-map-canvas');
              const bounds = map.getBoundingClientRect();
              return [...map.querySelectorAll('.city-map-building svg')].every(node => {
                const box = node.getBoundingClientRect();
                return box.left >= bounds.left && box.right <= bounds.right && box.top >= bounds.top && box.bottom <= bounds.bottom;
              });
            }""")
            page.screenshot(path=str(OUT / f"city-map-{width}-test-adapters.png"))
            for marker in region.locator(".leaflet-marker-icon").all():
                marker.focus()
                marker.press("Enter")
                popup_link = region.locator(".city-map-popup a").last
                expect(popup_link).to_be_visible()
                popup_link.focus()
                page.wait_for_function(
                    "node => { const a = node.getBoundingClientRect(); const b = node.closest('.city-map-canvas').getBoundingClientRect(); return a.left >= b.left && a.right <= b.right && a.top >= b.top && a.bottom <= b.bottom }",
                    arg=popup_link.element_handle(),
                )
                region.locator(".leaflet-popup-close-button").click()
        page.set_viewport_size({"width": 1366, "height": 768})
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        region.hover()
        old_zoom = region.locator(".leaflet-map-pane").get_attribute("style")
        page.mouse.wheel(0, -250)
        expect(region.locator(".leaflet-map-pane")).to_have_attribute("style", old_zoom)
        checkpoint(
            "city switching without new API; 1366/375/320; resize; reduced motion; wheel does not zoom"
        )

        page.get_by_role("button", name="Скрыть карту города").click()
        page.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
        page.get_by_role("button", name="Показать карту города").click()
        # Use a new zoom level; already decoded image URLs may be reused by Chromium.
        region.get_by_role("button", name="Приблизить", exact=True).click()
        expect(
            page.get_by_text("Не удалось загрузить часть подложки", exact=False)
        ).to_be_visible()
        expect(page.get_by_role("table")).to_be_visible()
        region.get_by_role("button", name="ЖК на этой точке: 2", exact=False).click()
        expect(
            region.get_by_role(
                "link", name="Открыть карточку ЖК: " + records[0]["name"], exact=True
            )
        ).to_be_visible()
        fixture["items"] = [{**record, "coordinates": None} for record in records]
        page.reload()
        page.get_by_role("button", name="Показать карту города").click()
        expect(page.get_by_text("Нет объектов для карты", exact=False)).to_be_visible()
        expect(page.get_by_role("table")).to_be_visible()
        checkpoint(
            "tile outage keeps selectable buildings; missing coordinates keep table and empty explanation"
        )

        fixture["items"] = records
        page.goto(BASE + "/")
        expect(
            page.get_by_role("button", name="Показать карту", exact=True)
        ).to_be_visible()
        expect(
            page.get_by_role("button", name="Показать карту города", exact=True)
        ).to_have_count(0)
        checkpoint("overview priority map remains separate")

        fresh = browser.new_context()
        fresh.route("**/*", local_only)
        failed_page = fresh.new_page()
        failed_page.on("pageerror", lambda error: errors.append(str(error)))
        failed_page.route("**/api/v1/complexes?*", catalog)
        held_chunks = []
        chunk_pattern = "**/src/features/city-map/CityBuildingsMap.tsx*"
        failed_page.route(chunk_pattern, lambda route: held_chunks.append(route))
        try:
            failed_page.goto(BASE + "/complexes")
            login(failed_page)
            with failed_page.expect_request(chunk_pattern):
                failed_page.get_by_role("button", name="Показать карту города").click()
            expect(
                failed_page.get_by_text("Загружаем модуль карты…", exact=True)
            ).to_be_visible()
            assert (
                failed_page.locator(".city-map-canvas").bounding_box()["height"] == 360
            )
            expect(failed_page.get_by_role("table")).to_be_visible()
            assert held_chunks
            for held_chunk in held_chunks:
                held_chunk.abort()
            expect(
                failed_page.get_by_text(
                    "Не удалось загрузить модуль карты", exact=False
                )
            ).to_be_visible()
            assert (
                failed_page.locator(".city-map-canvas").bounding_box()["height"] == 360
            )
            expect(failed_page.get_by_role("table")).to_be_visible()
            failed_page.get_by_role("button", name="Скрыть карту города").click()
            expect(
                failed_page.get_by_role("button", name="Показать карту города")
            ).to_have_attribute("aria-expanded", "false")
        finally:
            fresh.close()
        checkpoint("lazy module failure contained; registry and toggle remain usable")
        assert not errors, errors
        assert not external, external
        checkpoint(
            "no page errors / no external network; explicit local Auth/API/tile fixtures"
        )
    except Exception:
        page.screenshot(path=str(OUT / "failure.png"), full_page=True)
        (OUT / "failure.txt").write_text(page.locator("body").inner_text())
        raise
    finally:
        context.close()
        browser.close()
