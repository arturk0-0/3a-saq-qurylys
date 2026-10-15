import hashlib
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.models.analysis import AnalysisRequest, Hypothesis, HypothesisDecision
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.entities import Advertisement, Evidence
from app.services.files import FileService
from app.services.gemini import PROMPT_VERSION, GeminiClient
from app.services.workspace import WorkspaceService, audit_event, serialize


class AnalysisService:
    def __init__(
        self,
        workspace: WorkspaceService,
        client: GeminiClient,
        files: FileService,
        settings: Settings,
    ):
        self.workspace, self.client, self.files, self.settings = workspace, client, files, settings

    def analyze(self, ad_id: str, payload: AnalysisRequest, user: Principal) -> dict:
        self.client.check_config()
        run_id = str(payload.request_id)
        ad = Advertisement.model_validate(self.workspace.require_record("advertisements", ad_id))
        fingerprint = hashlib.sha256(
            f"{ad_id}:{payload.expected_version}:{payload.screenshot_id}".encode()
        ).hexdigest()
        now = utc_now()
        day = now.strftime("%Y%m%d")
        quota_ids = [f"global-{day}", f"user-{hashlib.sha256(user.uid.encode()).hexdigest()}-{day}"]

        def reserve(tx):
            existing = tx.get("analysisRuns", run_id)
            current = Advertisement.model_validate(
                self.workspace.require_record("advertisements", ad_id, tx)
            )
            counters = [tx.get("usageLimits", key) or {"id": key, "count": 0} for key in quota_ids]
            if existing:
                if existing["createdBy"] != user.uid or existing["fingerprint"] != fingerprint:
                    raise Conflict("Analysis request ID already used")
                if existing["status"] == "succeeded":
                    return existing
                raise Conflict(
                    "Analysis already attempted; refresh results before starting another"
                )
            if current.version != payload.expected_version:
                raise Conflict()
            if payload.screenshot_id and payload.screenshot_id not in current.attachment_ids:
                raise AppError(
                    422, "IMAGE_MISMATCH", "Select an image attached to this advertisement"
                )
            for counter, limit in zip(
                counters,
                [self.settings.ai_daily_global_limit, self.settings.ai_daily_user_limit],
                strict=True,
            ):
                if counter["count"] >= limit:
                    raise AppError(429, "AI_DAILY_LIMIT", "Daily analysis limit reached")
            run = {
                "id": run_id,
                "advertisementId": ad_id,
                "complexId": ad.complex_id,
                "createdBy": user.uid,
                "createdAt": now.isoformat(),
                "demo": ad.demo,
                "fingerprint": fingerprint,
                "status": "running",
                "model": self.settings.gemini_model,
                "promptVersion": PROMPT_VERSION,
                "hypothesisIds": [],
                "screenshotId": payload.screenshot_id,
            }
            tx.create("analysisRuns", run_id, run)
            for counter in counters:
                tx.set("usageLimits", counter["id"], {**counter, "count": counter["count"] + 1})
            return run

        run = self.workspace.store.atomic(reserve)
        if run["status"] == "succeeded":
            return run
        try:
            image = self.files.download(payload.screenshot_id) if payload.screenshot_id else None
            result = self.client.extract(ad.text, image)
            digest = hashlib.sha256(ad.text.encode() + (image[0] if image else b"")).hexdigest()
            screenshot = (
                Evidence.model_validate(
                    self.workspace.require_record("evidence", payload.screenshot_id)
                )
                if payload.screenshot_id
                else None
            )
            hypotheses, evidence = [], []
            for proposal in result.hypotheses:
                eid = uuid4().hex
                item = Evidence(
                    id=eid,
                    complex_id=ad.complex_id,
                    advertisement_id=ad.id,
                    type="screenshot" if screenshot else "advertisement",
                    source_url=ad.source_url,
                    source_reference=f"AI hypothesis; {PROMPT_VERSION}; unverified",
                    excerpt=proposal.quote,
                    captured_at=screenshot.captured_at if screenshot else ad.captured_at,
                    status="proposed",
                    demo=ad.demo,
                    storage_path=screenshot.storage_path if screenshot else None,
                    sha256=screenshot.sha256 if screenshot else None,
                    media_type=screenshot.media_type if screenshot else None,
                    size_bytes=screenshot.size_bytes if screenshot else None,
                )
                evidence.append(item)
                hypotheses.append(
                    Hypothesis(
                        id=uuid4().hex,
                        **proposal.model_dump(),
                        run_id=run_id,
                        complex_id=ad.complex_id,
                        advertisement_id=ad.id,
                        evidence_id=eid,
                        model=self.settings.gemini_model,
                        prompt_version=PROMPT_VERSION,
                        input_sha256=digest,
                        created_at=now,
                        demo=ad.demo,
                    )
                )
            completed = {
                **run,
                "status": "succeeded",
                "inputSha256": digest,
                "hypothesisIds": [h.id for h in hypotheses],
                "extraction": serialize(result),
                "completedAt": utc_now().isoformat(),
            }

            def save(tx):
                complex_ = self.workspace.complex(ad.complex_id, tx)
                event = audit_event(
                    user,
                    "advertisement",
                    ad_id,
                    "ai.analyze",
                    complex_,
                    {"runId": run_id, "count": len(hypotheses)},
                )
                for item in evidence:
                    tx.create("evidence", item.id, serialize(item))
                for item in hypotheses:
                    tx.create("aiHypotheses", item.id, serialize(item))
                tx.set("analysisRuns", run_id, completed)
                tx.create("auditLogs", event.id, serialize(event))

            self.workspace.store.atomic(save)
            return completed
        except Exception as exc:
            code = exc.code if isinstance(exc, AppError) else "ANALYSIS_FAILED"

            def fail(tx):
                saved = tx.get("analysisRuns", run_id)
                # A timeout during commit may have persisted the success; never overwrite it.
                if saved and saved["status"] == "running":
                    tx.set("analysisRuns", run_id, {**saved, "status": "failed", "errorCode": code})

            self.workspace.store.atomic(fail)
            raise

    def review(
        self, hypothesis_id: str, payload: HypothesisDecision, user: Principal
    ) -> Hypothesis:
        def operation(tx):
            hypothesis = Hypothesis.model_validate(
                self.workspace.require_record("aiHypotheses", hypothesis_id, tx)
            )
            complex_ = self.workspace.complex(hypothesis.complex_id, tx)
            if hypothesis.version != payload.expected_version or hypothesis.status != "proposed":
                raise Conflict()
            hypothesis.status = payload.decision
            hypothesis.reviewer, hypothesis.reviewed_at = user.uid, utc_now()
            hypothesis.notes, hypothesis.version = payload.notes, hypothesis.version + 1
            event = audit_event(
                user,
                "hypothesis",
                hypothesis_id,
                "ai.review",
                complex_,
                {"decision": payload.decision, "notes": payload.notes},
            )
            tx.set("aiHypotheses", hypothesis_id, serialize(hypothesis))
            tx.create("auditLogs", event.id, serialize(event))
            # Neither evidence nor factors become confirmed here.
            return hypothesis

        return self.workspace.store.atomic(operation)
