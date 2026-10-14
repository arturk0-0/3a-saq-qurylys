import argparse
import json
from pathlib import Path

from app.services.seed_data import SEED_VERSION, build_demo_seed


def main() -> None:
    parser = argparse.ArgumentParser(description="SAQ QURYLYS fictional DEMO dataset")
    parser.add_argument("command", choices=["validate", "export"])
    parser.add_argument("--output", type=Path, default=Path("../data/seed/demo.json"))
    args = parser.parse_args()
    seed = build_demo_seed()
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
