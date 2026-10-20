"""Compare deployed composite-index states with the exact checked-in query indexes."""

import argparse
import json
from pathlib import Path


def pending_indexes(expected, actual):
    pending = []
    for index in expected["indexes"]:
        group = index["collectionGroup"]
        fields = index["fields"]
        ready = False
        for remote in actual:
            name = remote.get("name", "")
            marker = f"/collectionGroups/{group}/indexes/"
            remote_fields = remote.get("fields", [])
            if not any(f["fieldPath"] == "__name__" for f in fields):
                remote_fields = [
                    f for f in remote_fields if f["fieldPath"] != "__name__"
                ]
            same = (
                marker in name
                and remote.get("queryScope", "COLLECTION")
                == index.get("queryScope", "COLLECTION")
                and remote_fields == fields
            )
            if same and remote.get("state") == "READY":
                ready = True
                break
        if not ready:
            pending.append(group + ":" + ",".join(f["fieldPath"] for f in fields))
    return pending


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("actual", type=Path)
    parser.add_argument("--expected", type=Path, default=Path("firestore.indexes.json"))
    args = parser.parse_args()
    remaining = pending_indexes(
        json.loads(args.expected.read_text()), json.loads(args.actual.read_text())
    )
    if remaining:
        print("Waiting for required READY indexes:", "; ".join(remaining))
        raise SystemExit(1)
    print("All required composite indexes are READY.")
