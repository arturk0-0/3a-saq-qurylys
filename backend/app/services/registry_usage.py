from app.core.errors import AppError
from app.models.common import utc_now


def reserve_registry_read(store):
    """One shared UTC quota for public registry operations, including failed attempts."""
    key = f"registry-{utc_now():%Y%m%d}"

    def reserve(tx):
        row = tx.get("monitorLimits", key) or {"id": key, "count": 0}
        if row["count"] >= 100:
            raise AppError(429, "REGISTRY_LIMIT", "Daily registry check limit reached")
        tx.set("monitorLimits", key, {**row, "count": row["count"] + 1})

    store.atomic(reserve)
