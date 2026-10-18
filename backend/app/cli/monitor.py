"""Owner-operated ADC worker: python -m app.cli.monitor [--watch]. Not an auth endpoint."""

import argparse
import json
import time

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.core.firebase import FirebaseRuntime
from app.models.auth import Principal
from app.repositories.firestore import FirestoreStore
from app.services.monitoring import MonitoringService
from app.services.workspace import WorkspaceService


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect due public monitoring sources")
    parser.add_argument(
        "--watch", action="store_true", help="Local long-running worker; not for Cloud Run HTTP"
    )
    args = parser.parse_args()
    try:
        settings = Settings()
    except ValidationError:
        print('{"errorCode":"MONITOR_SETTINGS_INVALID"}')
        return 1
    runtime = FirebaseRuntime(settings)
    # This is a named infrastructure actor with ADC, not an invented human reviewer.
    worker = Principal(uid="service-monitor-worker", role="analyst")
    try:
        service = MonitoringService(
            WorkspaceService(FirestoreStore(runtime.db()), demo_only=settings.firebase_demo_only),
            settings,
        )
        while True:
            results = service.run_due(worker)
            # IDs/counts/error codes only; no scraped texts, account names or keys.
            print(json.dumps(results), flush=True)
            if not args.watch:
                return int(any("errorCode" in row for row in results))
            time.sleep(60)
    except KeyboardInterrupt:
        return 0
    except AppError as error:
        print(json.dumps({"errorCode": error.code}))
        return 1
    except Exception:
        print('{"errorCode":"MONITOR_WORKER_FAILED"}')
        return 1
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
