"""Explicitly run a bounded paid Gemini evaluation, or list the corpus without requests."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.models.common import utc_now
from app.services.evaluation import evaluate_case
from app.services.gemini import PROMPT_VERSION, GeminiClient

CASES = Path(__file__).with_name("ai_cases.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка Gemini на вымышленных RU/KZ объявлениях")
    parser.add_argument(
        "--run", action="store_true", help="Запустить платные запросы (до 7 случаев)"
    )
    parser.add_argument("--limit", type=int, default=7, choices=range(1, 8))
    parser.add_argument("--output", type=Path, default=Path("artifacts/ai-evaluation/report.json"))
    args = parser.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))[: args.limit]
    if not args.run:
        for case in cases:
            print(
                f"{case['id']}: {case['language']} / {case['medium']}; "
                f"expected={case['expectedCodes']}"
            )
        print(
            "Запросы не выполнялись. Для реального прогона: --run. "
            "Каждый случай вызывает Gemini; возможен один повтор при временном сбое."
        )
        return 0
    try:
        settings = Settings()
        client = GeminiClient(settings)
        client.check_config()
    except (ValidationError, AppError):
        print("Проверьте GEMINI_API_KEY, GEMINI_MODEL и остальные настройки .env.")
        return 2
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.is_dir():
            raise OSError("Output must be a file")
        with tempfile.TemporaryFile(dir=args.output.parent):
            pass
    except OSError:
        print("Нет доступа к папке отчёта; задайте --output в доступной папке.")
        return 2
    results = []
    for case in cases:
        result = evaluate_case(case, client, image_directory=args.output.parent / "images")
        results.append(result)
        print(f"{case['id']}: {result['status']}", flush=True)
        # A provider/configuration error should not consume the rest of the small budget.
        if result["status"] == "error":
            break
    report = {
        "createdAt": utc_now().isoformat(),
        "model": settings.gemini_model,
        "promptVersion": PROMPT_VERSION,
        "corpusSha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "synthetic": True,
        "mode": "live-provider",
        "providerAnalysesAttempted": sum(row["providerAttempted"] for row in results),
        "requestedCases": len(cases),
        "executedCases": len(results),
        "counts": {
            status: sum(row["status"] == status for row in results)
            for status in ["passed", "failed", "error", "manual_review"]
        },
        "results": results,
        "limitations": "Малый опубликованный набор, не оценка точности на новых данных. "
        "Размытый скриншот всегда требует ручной проверки. "
        "Не проверяет Firebase, решения аналитика или баллы риска.",
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Отчёт сохранён; выполнено {len(results)} из {len(cases)} случаев.")
    return int(any(row["status"] in {"failed", "error"} for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
