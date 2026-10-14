from app.core.errors import Conflict
from app.models.common import utc_now
from app.repositories.store import Store, UnitOfWork
from app.services.seed_data import SEED_VERSION, build_demo_seed


def import_demo_seed(store: Store, actor_uid: str) -> dict:
    """Create-only, atomic seed import; existing analyst activity always wins."""
    seed = build_demo_seed()
    imported_at = utc_now().isoformat()

    def operation(tx: UnitOfWork):
        marker = tx.get("seedRuns", SEED_VERSION)
        if marker is not None:
            return {"version": SEED_VERSION, "alreadyImported": True, "created": 0, "skipped": 0}
        existing = {
            (collection, row["id"]): tx.get(collection, row["id"])
            for collection, rows in seed.items()
            for row in rows
        }
        if any(row is not None and not row.get("demo") for row in existing.values()):
            raise Conflict("A DEMO ID collides with a non-DEMO document; import was cancelled")
        created = 0
        skipped = 0
        for collection, rows in seed.items():
            for row in rows:
                if existing[(collection, row["id"])] is None:
                    tx.create(collection, row["id"], row)
                    created += 1
                else:
                    skipped += 1
        tx.create(
            "seedRuns",
            SEED_VERSION,
            {
                "id": SEED_VERSION,
                "actorUid": actor_uid,
                "importedAt": imported_at,
                "created": created,
                "skipped": skipped,
                "demo": True,
            },
        )
        tx.create(
            "auditLogs",
            f"seed-{SEED_VERSION}",
            {
                "id": f"seed-{SEED_VERSION}",
                "entityType": "seed",
                "entityId": SEED_VERSION,
                "action": "seed.import",
                "actorUid": actor_uid,
                "createdAt": imported_at,
                "demo": True,
                "details": {"created": created, "skipped": skipped},
            },
        )
        return {
            "version": SEED_VERSION,
            "alreadyImported": False,
            "created": created,
            "skipped": skipped,
        }

    return store.atomic(operation)
