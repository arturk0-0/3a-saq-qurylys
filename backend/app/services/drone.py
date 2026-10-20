"""Private drone inspections; no writes to advertisement evidence or risk factors."""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import AppError, Conflict, NotFound
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.drone import (
    AnalyzeInspection,
    CreateInspection,
    DroneInspection,
    DronePhoto,
    DroneReview,
    ReviewInspection,
)
from app.repositories.store import UnitOfWork
from app.services.drone_gemini import PROMPT_VERSION, DroneGeminiClient
from app.services.files import FileStorage, validate_image
from app.services.workspace import WorkspaceService, serialize

logger = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=5)


class _RejectedPhoto(Conflict):
    """A definite rejection before any transaction write, safe to remove own object."""


class DroneService:
    def __init__(
        self,
        workspace: WorkspaceService,
        storage: FileStorage,
        client: DroneGeminiClient,
        settings: Settings,
    ):
        self.workspace, self.store = workspace, workspace.store
        self.storage, self.client, self.settings = storage, client, settings
        self.scope = "demo" if workspace.demo_only else "live"

    def require(self, record_id: str, tx: UnitOfWork | None = None) -> DroneInspection:
        row = (tx or self.store).get("droneInspections", record_id)
        if not row or row["workspaceScope"] != self.scope:
            raise NotFound()
        item = DroneInspection.model_validate(row)
        if item.complex_id:
            self.workspace.complex(item.complex_id, tx)
        return item

    def event(self, item: DroneInspection, user: Principal, action: str, details: dict) -> dict:
        return dict(
            id=uuid4().hex,
            entityType="droneInspection",
            entityId=item.id,
            complexId=item.complex_id,
            actorUid=user.uid,
            createdAt=utc_now().isoformat(),
            action=action,
            demo=self.scope == "demo",
            details=details,
        )

    def public(self, item: DroneInspection) -> dict:
        result = serialize(item)
        result.pop("fingerprint")
        if result["photo"]:
            result["photo"].pop("storagePath")
        return result

    def get(self, record_id: str) -> dict:
        item = self.require(record_id)
        latest = self.store.get("droneRuns", item.latest_run_id) if item.latest_run_id else None
        stale = bool(
            latest
            and latest["status"] == "running"
            and utc_now() - datetime.fromisoformat(latest["createdAt"]) >= STALE_AFTER
        )
        return {
            **self.public(item),
            "latestRun": latest,
            "canAnalyze": bool(
                item.photo
                and item.analysis_count < 20
                and (not latest or latest["status"] != "running" or stale)
            ),
        }

    def list(self, cursor: str | None = None, limit: int = 20) -> dict:
        rows = self.store.list(
            "droneInspections",
            filters=[("workspaceScope", "==", self.scope)],
            after_id=cursor,
            limit=limit + 1,
            newest_first=True,
        )
        return {
            "items": [self.public(DroneInspection.model_validate(r)) for r in rows[:limit]],
            "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def create(self, payload: CreateInspection, user: Principal) -> dict:
        key = str(payload.request_id)
        fingerprint = hashlib.sha256(
            json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()

        def save(tx):
            existing = tx.get("droneInspections", key)
            complex_ = (
                self.workspace.complex(payload.complex_id, tx) if payload.complex_id else None
            )
            if existing:
                if (
                    existing["createdBy"] != user.uid
                    or existing["workspaceScope"] != self.scope
                    or existing["fingerprint"] != fingerprint
                ):
                    raise Conflict()
                return
            item = DroneInspection(
                id=key,
                workspace_scope=self.scope,
                title=payload.title,
                complex_id=payload.complex_id,
                complex_name=complex_.name if complex_ else None,
                captured_at=payload.captured_at,
                checklist=payload.checklist,
                created_at=utc_now(),
                created_by=user.uid,
                fingerprint=fingerprint,
            )
            event = self.event(item, user, "drone.create", {})
            tx.create("droneInspections", key, serialize(item))
            tx.create("auditLogs", event["id"], event)

        self.store.atomic(save)
        return self.get(key)

    def upload(
        self, record_id: str, version: int, data: bytes, media_type: str, user: Principal
    ) -> dict:
        item = self.require(record_id)
        if item.version != version or item.photo:
            raise Conflict("Photo already uploaded or inspection changed")
        validate_image(data, media_type)
        photo_id = uuid4().hex
        path = f"drone-inspections/{self.scope}/{item.id}/{photo_id}"
        photo = DronePhoto(
            id=photo_id,
            storage_path=path,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            media_type=media_type,
            uploaded_at=utc_now(),
        )
        self.storage.put(path, data, media_type)

        def save(tx):
            current = self.require(record_id, tx)
            if current.version != version or current.photo:
                raise _RejectedPhoto()
            current.photo, current.status = photo, "ready"
            current.version += 1
            event = self.event(current, user, "drone.photo.upload", {"sha256": photo.sha256})
            tx.set("droneInspections", record_id, serialize(current))
            tx.create("auditLogs", event["id"], event)

        try:
            self.store.atomic(save)
        except _RejectedPhoto:
            try:
                self.storage.delete(path)
            except Exception:
                logger.error("Drone upload cleanup failed; inspect private unreferenced objects")
            raise
        except Exception:
            logger.warning(
                "Drone upload commit uncertain; private object retained for reconciliation"
            )
            raise
        return self.get(record_id)

    def download(self, record_id: str) -> tuple[bytes, str]:
        item = self.require(record_id)
        if not item.photo:
            raise AppError(404, "NO_FILE", "Photo has not been uploaded")
        photo = item.photo
        if photo.storage_path != f"drone-inspections/{self.scope}/{item.id}/{photo.id}":
            raise AppError(502, "FILE_INTEGRITY", "Invalid photo reference")
        data = self.storage.get(photo.storage_path)
        if len(data) != photo.size_bytes or hashlib.sha256(data).hexdigest() != photo.sha256:
            raise AppError(502, "FILE_INTEGRITY", "Stored photo failed integrity verification")
        return data, photo.media_type

    def runs(self, record_id: str, cursor: str | None = None, limit: int = 20) -> dict:
        self.require(record_id)
        rows = self.store.list(
            "droneRuns",
            filters=[("inspectionId", "==", record_id)],
            after_id=cursor,
            limit=limit + 1,
            newest_first=True,
        )
        return {
            "items": rows[:limit],
            "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def analyze(self, record_id: str, payload: AnalyzeInspection, user: Principal) -> dict:
        run_id, now = str(payload.request_id), utc_now()
        fingerprint = hashlib.sha256(f"{record_id}:{payload.expected_version}".encode()).hexdigest()
        day = now.strftime("%Y%m%d")
        quota_ids = [f"global-{day}", f"user-{hashlib.sha256(user.uid.encode()).hexdigest()}-{day}"]

        def reserve(tx):
            item = self.require(record_id, tx)
            old = tx.get("droneRuns", run_id)
            latest = tx.get("droneRuns", item.latest_run_id) if item.latest_run_id else None
            counters = [tx.get("usageLimits", key) or {"id": key, "count": 0} for key in quota_ids]
            if old:
                if old["createdBy"] != user.uid or old["fingerprint"] != fingerprint:
                    raise Conflict("Request identifier already used")
                if old["status"] == "succeeded":
                    return False, item, old
                raise Conflict("Analysis already attempted; inspect saved results")
            if item.version != payload.expected_version:
                raise Conflict()
            if not item.photo:
                raise AppError(422, "DRONE_PHOTO_REQUIRED", "Upload a photo first")
            if item.analysis_count >= 20:
                raise AppError(409, "DRONE_LIMIT", "Inspection analysis limit reached")
            if latest and latest["status"] == "running":
                if now - datetime.fromisoformat(latest["createdAt"]) < STALE_AFTER:
                    raise AppError(409, "DRONE_BUSY", "Inspection is already being analyzed")
            self.client.check_config()
            for counter, limit in zip(
                counters,
                [self.settings.ai_daily_global_limit, self.settings.ai_daily_user_limit],
                strict=True,
            ):
                if counter["count"] >= limit:
                    raise AppError(429, "AI_DAILY_LIMIT", "Daily analysis limit reached")
            run = dict(
                id=run_id,
                inspectionId=record_id,
                workspaceScope=self.scope,
                createdBy=user.uid,
                createdAt=now.isoformat(),
                status="running",
                model=self.settings.gemini_model,
                promptVersion=PROMPT_VERSION,
                fingerprint=fingerprint,
                photoSha256=item.photo.sha256,
                checklist=[serialize(c) for c in item.checklist],
                result=None,
                errorCode=None,
                capturedAt=item.captured_at.isoformat() if item.captured_at else None,
            )
            if latest and latest["status"] == "running":
                tx.set(
                    "droneRuns",
                    latest["id"],
                    {
                        **latest,
                        "status": "failed",
                        "errorCode": "DRONE_INTERRUPTED",
                        "completedAt": now.isoformat(),
                    },
                )
            item.latest_run_id, item.status, item.last_error = run_id, "analyzing", None
            item.analysis_count += 1
            item.version += 1
            event = self.event(item, user, "drone.analyze.start", {"runId": run_id})
            tx.create("droneRuns", run_id, run)
            tx.set("droneInspections", record_id, serialize(item))
            for counter in counters:
                tx.set("usageLimits", counter["id"], {**counter, "count": counter["count"] + 1})
            tx.create("auditLogs", event["id"], event)
            return True, item, run

        reserved, item, run = self.store.atomic(reserve)
        if not reserved:
            return self.get(record_id)
        try:
            result = self.client.inspect(self.download(record_id), item.checklist)

            def complete(tx):
                current = self.require(record_id, tx)
                saved = tx.get("droneRuns", run_id)
                if current.latest_run_id != run_id or saved["status"] != "running":
                    raise Conflict("A newer inspection run replaced this result")
                current.status = "analyzed"
                current.version += 1
                event = self.event(current, user, "drone.analyze.complete", {"runId": run_id})
                tx.set(
                    "droneRuns",
                    run_id,
                    {
                        **run,
                        "status": "succeeded",
                        "result": serialize(result),
                        "completedAt": utc_now().isoformat(),
                    },
                )
                tx.set("droneInspections", record_id, serialize(current))
                tx.create("auditLogs", event["id"], event)

            self.store.atomic(complete)
        except Exception as error:
            code = error.code if isinstance(error, AppError) else "DRONE_ANALYSIS_FAILED"

            def fail(tx):
                saved = tx.get("droneRuns", run_id)
                current = self.require(record_id, tx)
                if not saved or saved["status"] != "running":
                    return
                event = self.event(
                    current, user, "drone.analyze.failed", {"runId": run_id, "code": code}
                )
                tx.set(
                    "droneRuns",
                    run_id,
                    {
                        **saved,
                        "status": "failed",
                        "errorCode": code,
                        "completedAt": utc_now().isoformat(),
                    },
                )
                if current.latest_run_id == run_id:
                    current.status, current.last_error = "failed", code
                    current.version += 1
                    tx.set("droneInspections", record_id, serialize(current))
                tx.create("auditLogs", event["id"], event)

            self.store.atomic(fail)
            raise
        return self.get(record_id)

    def review(self, record_id: str, payload: ReviewInspection, user: Principal) -> dict:
        def save(tx):
            item = self.require(record_id, tx)
            run = tx.get("droneRuns", payload.run_id)
            if item.version != payload.expected_version or item.latest_run_id != payload.run_id:
                raise Conflict()
            if not run or run["inspectionId"] != record_id or run["status"] != "succeeded":
                raise AppError(422, "DRONE_REVIEW_UNAVAILABLE", "Review a completed current run")
            if len(item.reviews) >= 20:
                raise AppError(409, "DRONE_LIMIT", "Inspection review history is full")
            review = DroneReview(
                run_id=payload.run_id,
                decision=payload.decision,
                notes=payload.notes,
                reviewer=user.uid,
                reviewed_at=utc_now(),
            )
            item.reviews.append(review)
            item.status = "reviewed"
            item.version += 1
            event = self.event(item, user, "drone.review", serialize(review))
            tx.set("droneInspections", record_id, serialize(item))
            tx.create("auditLogs", event["id"], event)

        self.store.atomic(save)
        return self.get(record_id)
