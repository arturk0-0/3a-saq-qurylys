"""Explicit local adapters, never loaded by the production app."""

import json

import httpx
from app.api.drone import drone_service
from app.services.drone import DroneService
from app.services.drone_gemini import DroneGeminiClient
from local_api import app, files, settings, workspace


def model(request):
    data = json.loads(request.content)
    assert request.url.host == "generativelanguage.googleapis.com"
    checklist = json.loads(data["contents"][0]["parts"][0]["text"])["checklist"]
    result = {
        "observations": [
            {
                "criterionId": c["id"],
                "visibility": ["visible", "not_visible", "uncertain"][i % 3],
                "explanation": "LOCAL QA: синтетическое наблюдение, не результат реального ИИ.",
            }
            for i, c in enumerate(checklist)
        ],
        "summary": "LOCAL QA: три статуса для проверки интерфейса.",
        "limitations": "Синтетический кадр и MockTransport. Реальные строительные нормы не проверялись.",
    }
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [{"text": json.dumps(result, ensure_ascii=False)}]
                    },
                }
            ]
        },
    )


service = DroneService(
    workspace,
    files.storage,
    DroneGeminiClient(settings, httpx.MockTransport(model)),
    settings,
)
app.dependency_overrides[drone_service] = lambda: service
