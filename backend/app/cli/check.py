"""python -m app.cli.check [--online] [--require-ai]. Does not run paid generation."""

import argparse
import json
from dataclasses import asdict

from pydantic import ValidationError

from app.core.config import Settings
from app.services.readiness import check_connections


def main() -> int:
    parser = argparse.ArgumentParser(description="SAQ QURYLYS: безопасная диагностика подключения")
    parser.add_argument(
        "--online", action="store_true", help="Проверить сервисы read-only запросами"
    )
    parser.add_argument(
        "--require-ai", action="store_true", help="Отсутствие Gemini считать ошибкой"
    )
    parser.add_argument("--json", action="store_true", help="Вывести машинно-читаемый отчёт")
    args = parser.parse_args()
    try:
        settings = Settings()
    except ValidationError:
        # str(ValidationError) includes the original settings values. Never print it.
        print("Некорректные настройки .env. Проверьте типы значений по .env.example.")
        return 1
    checks = check_connections(settings, online=args.online, require_ai=args.require_ai)
    if args.json:
        print(json.dumps([asdict(check) for check in checks], ensure_ascii=False, indent=2))
    else:
        for check in checks:
            print(f"[{check.status.upper()}] {check.name}: {check.message}")
        print(
            "Проверка не подтверждает вход аналитика, правила клиентов, загрузку файлов, "
            "наличие seed или качество генерации AI. Полный сценарий: docs/demo-scenarios.md."
        )
    return int(any(check.status == "failed" for check in checks))


if __name__ == "__main__":
    raise SystemExit(main())
