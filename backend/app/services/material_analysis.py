"""Durable bounded analysis queue. No silent retry of an uncertain paid outcome."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.errors import AppError
from app.models.common import utc_now
from app.services.gemini import PROMPT_VERSION
from app.services.material_projection import all_rows, digest


def hypotheses(job):
    result = (job.get("extraction") or {}).get("hypotheses", [])
    unique = {}
    for h in result:
        hid = digest(job["id"] + h["code"] + h["quote"])
        unique[hid] = {
            "id": hid,
            "code": h["code"],
            "quote": h["quote"],
            "explanation": h["explanation"],
            "occurrenceId": job["occurrenceId"],
            "decision": "pending",
            "_jobId": job["id"],
        }
    return list(unique.values())


class MaterialProcessor:
    def __init__(self, workspace, client, files, settings):
        self.workspace, self.store = workspace, workspace.store
        self.client, self.files, self.settings = client, files, settings

    def process(self, user, limit=3, material_id=None):
        outcomes = []
        # ID cursor scan is deliberate; sort oldest first so small batches cannot starve work.
        jobs = list(all_rows(self.store, "materialJobs", [("status", "in", ["queued", "running"])]))
        jobs.sort(key=lambda r: (r["createdAt"], r["id"]))
        for candidate in jobs:
            if material_id and candidate["materialId"] != material_id:
                continue
            if self.workspace.demo_only and candidate["workspaceScope"] == "live":
                continue
            if len(outcomes) >= limit:
                break
            if (
                candidate.get("nextAttemptAt")
                and candidate["nextAttemptAt"] > utc_now().isoformat()
            ):
                continue
            now = utc_now()
            if candidate["status"] == "running":
                if candidate.get("leaseUntil") and candidate["leaseUntil"] > now.isoformat():
                    continue
                self._finish(candidate, None, "AI_OUTCOME_UNKNOWN")
                outcomes.append({"jobId": candidate["id"], "errorCode": "AI_OUTCOME_UNKNOWN"})
                continue
            try:
                self.client.check_config()
            except AppError as error:
                self._unavailable(candidate, error.code)
                outcomes.append({"jobId": candidate["id"], "errorCode": error.code})
                continue
            attempt = str(uuid4())

            def claim(tx, candidate=candidate, now=now, attempt=attempt):
                current = tx.get("materialJobs", candidate["id"])
                if not current or current["status"] != "queued":
                    return None
                run = {
                    **current,
                    "status": "running",
                    "attemptToken": attempt,
                    "leaseUntil": (now + timedelta(minutes=10)).isoformat(),
                    "errorCode": None,
                    "model": self.settings.gemini_model,
                    "promptVersion": PROMPT_VERSION,
                }
                tx.set("materialJobs", run["id"], run)
                return run

            job = self.store.atomic(claim)
            if job is None:
                continue
            try:
                image = (
                    self.files.download(job["screenshotId"]) if job.get("screenshotId") else None
                )
                from app.services.material_provider import cached_extract

                result = cached_extract(
                    self.workspace,
                    self.settings,
                    self.client,
                    job["text"],
                    image,
                    user,
                    job["workspaceScope"],
                )
                if not image and any(h.quote not in job["text"] for h in result.hypotheses):
                    raise AppError(502, "AI_INVALID_RESPONSE", "Unanchored text quote")
                self._finish(job, result.model_dump(mode="json", by_alias=True), None)
                outcomes.append({"jobId": job["id"], "status": "ready"})
            except Exception as error:
                code = error.code if isinstance(error, AppError) else "ANALYSIS_FAILED"
                if code == "AI_DAILY_LIMIT":
                    self._defer(job, code)
                elif code == "AI_BUSY":
                    self._defer(job, code, minutes=1)
                else:
                    self._finish(job, None, code)
                outcomes.append({"jobId": job["id"], "errorCode": code})
        return outcomes

    def _defer(self, job, code, minutes=None):
        now = utc_now()
        until = (
            now + timedelta(minutes=minutes)
            if minutes
            else datetime.combine((now + timedelta(days=1)).date(), datetime.min.time(), UTC)
        )

        def save(tx):
            current = tx.get("materialJobs", job["id"])
            if current and current.get("attemptToken") == job.get("attemptToken"):
                tx.set(
                    "materialJobs",
                    job["id"],
                    {
                        **current,
                        "status": "queued",
                        "errorCode": code,
                        "nextAttemptAt": until.isoformat(),
                        "leaseUntil": None,
                    },
                )

        self.store.atomic(save)

    def _unavailable(self, job, code):
        def save(tx):
            current = tx.get("materialJobs", job["id"])
            if current and current["status"] == "queued":
                tx.set(
                    "materialJobs", job["id"], {**current, "status": "failed", "errorCode": code}
                )

        self.store.atomic(save)

    def _finish(self, job, result, code):
        def save(tx):
            current = tx.get("materialJobs", job["id"])
            group = tx.get("materials", job["materialId"])
            if (
                not current
                or current["status"] != "running"
                or current.get("attemptToken") != job.get("attemptToken")
            ):
                return
            updated = {
                **current,
                "status": "failed" if code else "ready",
                "extraction": result,
                "errorCode": code,
                "leaseUntil": None,
                "completedAt": utc_now().isoformat(),
            }
            tx.set("materialJobs", job["id"], updated)
            if group and job["id"] in group["inputIds"]:
                tx.set("materials", group["id"], {**group, "version": group["version"] + 1})

        self.store.atomic(save)
