import argparse
import json
from pathlib import Path

from app.services.seed_data import SEED_VERSION, build_demo_seed


def main() -> None:
    parser = argparse.ArgumentParser(description="SAQ QURYLYS fictional DEMO dataset")
    parser.add_argument("command", choices=["validate", "export", "import"])
    parser.add_argument("--output", type=Path, default=Path("../data/seed/demo.json"))
    parser.add_argument("--project-confirm", help="Exact Firebase project ID required for import")
    parser.add_argument("--apply", action="store_true", help="Actually create missing DEMO records")
    args = parser.parse_args()
    seed = build_demo_seed()
    if args.command == "import":
        from app.core.config import Settings
        from app.core.firebase import FirebaseRuntime
        from app.repositories.firestore import FirestoreStore
        from app.services.seed import import_demo_seed

        settings = Settings()
        if not args.apply or args.project_confirm != settings.firebase_project_id:
            parser.error(
                "Import requires --apply and --project-confirm matching FIREBASE_PROJECT_ID"
            )
        if not settings.firebase_enabled or not settings.firebase_demo_only:
            parser.error("Import requires FIREBASE_ENABLED=true and FIREBASE_DEMO_ONLY=true")
        runtime = FirebaseRuntime(settings)
        try:
            result = import_demo_seed(FirestoreStore(runtime.db()), "admin-cli")
            print(json.dumps(result, ensure_ascii=False))
        finally:
            runtime.close()
        return
    if args.command == "export":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"version": SEED_VERSION, "collections": seed}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {"version": SEED_VERSION, "counts": {key: len(value) for key, value in seed.items()}},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
