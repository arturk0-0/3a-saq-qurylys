"""Offline, synthetic LINK-01/02 demonstration; no .env, database, AI or network."""

import json
from dataclasses import asdict

from app.services.ad_trace import TraceDocument, propose_links


def main() -> int:
    # Intentionally non-routable fictional prefix and reserved .invalid domains.
    ads = (
        TraceDocument(
            "demo-trace-account-a",
            "DEMO — Учебный берег. Контакт +7 (000) 000-00-01. example.invalid",
        ),
        TraceDocument(
            "demo-trace-account-b", "DEMO — Учебный берег. WhatsApp: https://wa.me/70000000001"
        ),
        TraceDocument("demo-trace-account-c", "DEMO — Другой проект. Телефон 8 (000) 000-00-02."),
    )
    result = propose_links(ads, known_names=["ЖК Учебный берег"])
    print(
        json.dumps(
            {
                "demo": True,
                "notice": (
                    "OFFLINE DEMO: совпадение требует проверки; общность владельца не установлена; "
                    "баллы R1–R6 не меняются."
                ),
                "result": asdict(result),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
