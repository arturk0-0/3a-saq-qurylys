"""Explicit synthetic providers; no HTTP clients, paid requests, or image recognition."""

import hashlib
import re

from app.models.analysis import ExtractedHypothesis, Extraction
from app.models.common import utc_now
from app.models.drone import DroneObservation, DroneResult
from app.models.monitoring import Observation
from app.services.public_sources import FetchResult


class LocalAnalysis:
    def check_config(self):
        pass

    def extract(self, text, image=None):
        proposals = []
        if not image:
            for code, pattern in [("R2", r"депозит|внесите|задаток"), ("R3", r"строящ|строится")]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    proposals.append(
                        ExtractedHypothesis(
                            code=code,
                            quote=text[match.start() : min(match.start() + 180, len(text))],
                            explanation="Локальный текстовый пример по ключевым словам, не Gemini.",
                        )
                    )
        return Extraction(
            hypotheses=proposals,
            mentioned_complexes=[],
            payment_terms=[],
            uncertainty=(
                "Локальная демонстрация. Настоящий ИИ не вызывался. "
                "Изображение сохранено, но его содержимое не распознавалось."
                if image
                else "Локальная демонстрация правил по словам. Не результат ИИ или правовой вывод."
            ),
        )


class LocalDrone(LocalAnalysis):
    def inspect(self, image, checklist):
        return DroneResult(
            observations=[
                DroneObservation(
                    criterion_id=c.id,
                    visibility="uncertain",
                    explanation="В локальном деморежиме фото не анализируется ИИ.",
                )
                for c in checklist
            ],
            summary="Учебный отчёт. Проверьте фото вручную или используйте облачную версию.",
            limitations="Нет распознавания снимка или проверки строительных норм.",
        )


class LocalCollector:
    def fetch(self, source, before_search=None):
        text = (
            "DEMO — вымышленная реклама. Өскемен, Усть-Каменогорск. "
            "Квартиры в строящемся ЖК Янтарный берег. Для бронирования внесите депозит. "
            "Учебный материал локального деморежима, не реальная публикация."
        )
        item = Observation(
            original_url="https://demo.invalid/monitor/" + source.id,
            title="DEMO — учебная реклама жилья",
            text=text,
            account="DEMO — вымышленный источник",
            content_kind={
                "telegram": "telegram_post",
                "instagram_ads": "instagram_ad",
                "web_search": "search_snippet",
            }[source.kind],
            published_at=utc_now(),
        )
        return FetchResult(
            items=[item],
            discovery_url="https://demo.invalid/local-collection",
            response_sha256=hashlib.sha256(text.encode()).hexdigest(),
            limited=False,
        )
