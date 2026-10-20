"""Collect public observations; reserve work/quotas before external effects."""

import hashlib
import json
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.core.errors import AppError, Conflict, NotFound
from app.models.analysis import Hypothesis
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.entities import Advertisement, Evidence
from app.models.monitoring import (
    BasisReview,
    ItemAnalyze,
    ItemAttach,
    ItemBasisReview,
    ItemReview,
    MonitorItem,
    MonitorRun,
    MonitorSource,
    RegistryDocument,
    SourceInput,
    SourceUpdate,
)
from app.services.gemini import PROMPT_VERSION, GeminiClient
from app.services.public_sources import (
    PublicCollector,
    date_or_none,
    normalize_target,
    relevance,
    safe_original_url,
)
from app.services.registries import RegistryClient
from app.services.registry_usage import reserve_registry_read
from app.services.searchapi import MonitoringCollector
from app.services.workspace import WorkspaceService, audit_event, serialize


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def monitor_event(user, entity_id, action, details=None):
    return {
        "id": uuid4().hex,
        "entityId": entity_id,
        "action": action,
        "actorUid": user.uid,
        "createdAt": utc_now().isoformat(),
        "details": details or {},
    }


class MonitoringService:
    def __init__(
        self,
        workspace: WorkspaceService,
        settings: Settings,
        collector: PublicCollector | None = None,
        client: GeminiClient | None = None,
        registry: RegistryClient | None = None,
    ):
        self.workspace, self.store, self.settings = workspace, workspace.store, settings
        self.collector = collector or MonitoringCollector(settings)
        self.client = client or GeminiClient(settings)
        self.registry = registry or RegistryClient()

    def require(self, collection, record_id, tx=None):
        row = (tx or self.store).get(collection, record_id)
        if row is None:
            raise NotFound()
        return row

    def sources(self):
        return {"items": self.store.list("monitorSources", limit=20)}

    def status(self):
        counter = self.store.get("monitorLimits", f"fetch-{utc_now():%Y%m%d}") or {}
        worker = self.store.get("monitorLimits", "worker") or {}
        provider = self.store.get("monitorLimits", "searchapi") or {}
        provider_day = self.store.get("monitorLimits", f"searchapi-{utc_now():%Y%m%d}") or {}
        return {
            "workerLastTickAt": worker.get("lastTickAt"),
            "dailyFetchUsed": counter.get("count", 0),
            "dailyFetchLimit": self.settings.monitor_daily_fetch_limit,
            "maxAutoAiPerRun": 1,
            "liveRegistryEnabled": not self.workspace.demo_only,
            "instagramTargetedAds": "configured"
            if self.settings.searchapi_enabled
            and self.settings.searchapi_api_key.get_secret_value()
            else "not_connected",
            "searchApi": {
                "scheduled": self.settings.searchapi_schedule_enabled,
                "dailyLimit": self.settings.searchapi_daily_limit,
                "dailyUsed": provider_day.get("count", 0),
                "creditReserve": self.settings.searchapi_credit_reserve,
                "creditsObservedBefore": provider.get("creditsObservedBefore"),
                "checkedAt": provider.get("checkedAt"),
                "unsettledAttempts": len(provider.get("pendingSearches", {})),
            },
        }

    def history(self, item_id, cursor=None, limit=20):
        self.item(item_id)
        rows = self.store.list(
            "monitorEvents",
            filters=[("entityId", "==", item_id)],
            after_id=cursor,
            limit=limit + 1,
            newest_first=True,
        )
        return {
            "items": rows[:limit],
            "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def create_source(self, payload: SourceInput, user: Principal):
        target = normalize_target(payload.kind, payload.target)
        key = sha(f"{payload.kind}:{target.casefold()}")
        source = MonitorSource(
            **payload.model_dump(exclude={"target"}),
            target=target,
            id=key,
            created_at=utc_now(),
            created_by=user.uid,
        )
        event = monitor_event(user, key, "source.create")

        def save(tx):
            existing = tx.get("monitorSources", key)
            count = tx.get("monitorLimits", "sources") or {"id": "sources", "count": 0}
            if existing:
                return existing
            if count["count"] >= 20:
                raise AppError(429, "MONITOR_SOURCE_LIMIT", "Maximum 20 monitoring sources")
            tx.create("monitorSources", key, serialize(source))
            tx.set("monitorLimits", "sources", {**count, "count": count["count"] + 1})
            tx.create("monitorEvents", event["id"], event)
            return serialize(source)

        return self.store.atomic(save)

    def update_source(self, source_id: str, payload: SourceUpdate, user: Principal):
        def update(tx):
            source = MonitorSource.model_validate(self.require("monitorSources", source_id, tx))
            if source.version != payload.expected_version or (
                source.lease_until and source.lease_until > utc_now()
            ):
                raise Conflict("Refresh source; collection may be running")
            updated = source.model_copy(
                update={
                    "enabled": payload.enabled,
                    "auto_analyze": payload.auto_analyze,
                    "version": source.version + 1,
                }
            )
            event = monitor_event(user, source_id, "source.update", payload.model_dump())
            tx.set("monitorSources", source_id, serialize(updated))
            tx.create("monitorEvents", event["id"], event)
            return serialize(updated)

        return self.store.atomic(update)

    def items(self, status=None, cursor=None, limit=30):
        rows = self.store.list(
            "monitorItems",
            filters=[("status", "in", ["new", "investigating"])]
            if status == "active"
            else [("status", "==", status)]
            if status
            else [],
            after_id=cursor,
            limit=limit + 1,
            newest_first=True,
        )
        return {
            "items": rows[:limit],
            "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def runs(self, cursor=None, limit=20):
        rows = self.store.list("monitorRuns", after_id=cursor, limit=limit + 1, newest_first=True)
        return {
            "items": rows[:limit],
            "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def item(self, item_id, tx=None):
        return MonitorItem.model_validate(self.require("monitorItems", item_id, tx))

    def _reserve(self, source_id, user):
        now = utc_now()
        run = MonitorRun(id=uuid4().hex, source_id=source_id, created_at=now, actor_uid=user.uid)
        quota_key = f"fetch-{now:%Y%m%d}"

        def reserve(tx):
            source = MonitorSource.model_validate(self.require("monitorSources", source_id, tx))
            counter = tx.get("monitorLimits", quota_key) or {"id": quota_key, "count": 0}
            if not source.enabled:
                raise AppError(409, "MONITOR_PAUSED", "Source is paused")
            if source.lease_until and source.lease_until > now:
                raise AppError(409, "MONITOR_BUSY", "Source collection is running")
            if source.next_run_at and source.next_run_at > now:
                raise AppError(429, "MONITOR_NOT_DUE", "Source interval has not elapsed")
            if counter["count"] >= self.settings.monitor_daily_fetch_limit:
                raise AppError(429, "MONITOR_DAILY_LIMIT", "Daily collection limit reached")
            abandoned = (
                tx.get("monitorRuns", source.active_run_id) if source.active_run_id else None
            )
            provider = provider_day = None
            provider_day_key = f"searchapi-{now:%Y%m%d}"
            if source.kind == "instagram_ads":
                if not self.settings.searchapi_enabled:
                    raise AppError(503, "SEARCHAPI_DISABLED", "Meta provider is disabled")
                if not self.settings.searchapi_api_key.get_secret_value():
                    raise AppError(
                        503, "SEARCHAPI_NOT_CONFIGURED", "Meta provider is not configured"
                    )
                provider = tx.get("monitorLimits", "searchapi") or {"id": "searchapi"}
                provider_day = tx.get("monitorLimits", provider_day_key) or {
                    "id": provider_day_key,
                    "count": 0,
                }
                lease = date_or_none(provider.get("leaseUntil"))
                if lease and lease > now:
                    raise AppError(409, "SEARCHAPI_BUSY", "Another Meta search is running")
                if provider_day["count"] >= self.settings.searchapi_daily_limit:
                    raise AppError(429, "SEARCHAPI_DAILY_LIMIT", "Daily Meta search limit reached")
            updated = source.model_copy(
                update={
                    "active_run_id": run.id,
                    "lease_until": now + timedelta(minutes=10),
                    "last_run_at": now,
                    "next_run_at": now + timedelta(minutes=source.interval_minutes),
                }
            )
            if abandoned and abandoned["status"] == "running":
                tx.set(
                    "monitorRuns",
                    abandoned["id"],
                    {
                        **abandoned,
                        "status": "failed",
                        "errorCode": "MONITOR_LEASE_EXPIRED",
                        "completedAt": now.isoformat(),
                    },
                )
            tx.set("monitorSources", source_id, serialize(updated))
            if provider is not None:
                tx.set(
                    "monitorLimits",
                    "searchapi",
                    {
                        **provider,
                        "activeRunId": run.id,
                        "leaseUntil": (now + timedelta(minutes=10)).isoformat(),
                    },
                )
                tx.set(
                    "monitorLimits",
                    provider_day_key,
                    {
                        **provider_day,
                        "count": provider_day["count"] + 1,
                    },
                )
            tx.set("monitorLimits", quota_key, {**counter, "count": counter["count"] + 1})
            tx.create("monitorRuns", run.id, serialize(run))
            return updated

        return self.store.atomic(reserve), run

    def _authorize_provider_search(self, source, run, credits):
        """Recheck lease after account HTTP; retain a debit for unknown external outcomes."""
        now = utc_now()

        def authorize(tx):
            current = MonitorSource.model_validate(self.require("monitorSources", source.id, tx))
            provider = self.require("monitorLimits", "searchapi", tx)
            lease = date_or_none(provider.get("leaseUntil"))
            if (
                provider.get("activeRunId") != run.id
                or current.active_run_id != run.id
                or lease is None
                or lease <= now
                or current.lease_until is None
                or current.lease_until <= now
            ):
                raise AppError(409, "SEARCHAPI_BUSY", "Meta collection lease was lost")
            pending = dict(provider.get("pendingSearches", {}))
            if run.id in pending:
                raise Conflict("Meta search already reserved; do not retry")
            if credits - len(pending) <= self.settings.searchapi_credit_reserve:
                raise AppError(429, "SEARCHAPI_RESERVE", "Keep the reserved Meta search credits")
            pending[run.id] = now.isoformat()
            tx.set(
                "monitorLimits",
                "searchapi",
                {
                    **provider,
                    "pendingSearches": pending,
                    "creditsObservedBefore": credits,
                    "checkedAt": now.isoformat(),
                },
            )

        self.store.atomic(authorize)

    def _ingest(self, source, run, observation, result):
        original = safe_original_url(observation.original_url)
        if not original:
            return None, False
        region, housing, payment = relevance(observation.text)
        if not region or not housing:
            return None, False
        now = utc_now()
        digest = sha(observation.text)
        revision = f"{original}:{digest}"
        if observation.content_kind == "instagram_ad":
            # Signed CDN query strings/hosts can rotate without a changed creative.
            media_paths = sorted({(m.kind, urlsplit(m.url).path) for m in observation.media})
            revision += ":" + sha(json.dumps(media_paths))
        key = sha(revision)
        item = MonitorItem(
            **observation.model_dump(exclude={"original_url"}),
            original_url=original,
            id=key,
            source_id=source.id,
            source_ids=[source.id],
            discovery_url=result.discovery_url,
            text_sha256=digest,
            response_sha256=result.response_sha256,
            revision_key=sha(original),
            created_at=now,
            last_seen_at=now,
            region_matches=region,
            housing_matches=housing,
            payment_matches=payment,
        )

        def save(tx):
            current_source = MonitorSource.model_validate(
                self.require("monitorSources", source.id, tx)
            )
            existing = tx.get("monitorItems", key)
            if (
                current_source.active_run_id != run.id
                or current_source.lease_until is None
                or current_source.lease_until < now
            ):
                raise Conflict("Collection lease expired; refresh source")
            from app.services.material_projection import monitor_occurrence, stage_occurrence

            if existing:
                old = MonitorItem.model_validate(existing)
                seen = old.model_copy(
                    update={
                        "last_seen_at": now,
                        "source_ids": sorted(set([*old.source_ids, source.id]))[:20],
                    }
                )
                stage_occurrence(tx, monitor_occurrence(seen))
                tx.set("monitorItems", key, serialize(seen))
                return seen, False
            stage_occurrence(tx, monitor_occurrence(item))
            tx.create("monitorItems", key, serialize(item))
            return item, True

        return self.store.atomic(save)

    def _finish(self, source, run):
        def finish(tx):
            current = MonitorSource.model_validate(self.require("monitorSources", source.id, tx))
            provider = (
                tx.get("monitorLimits", "searchapi") if source.kind == "instagram_ads" else None
            )
            if provider:
                updates = {}
                if provider.get("activeRunId") == run.id:
                    updates.update(leaseUntil=None, activeRunId=None)
                if run.provider_credits_before is not None:
                    pending = dict(provider.get("pendingSearches", {}))
                    pending.pop(run.id, None)
                    updates["pendingSearches"] = pending
                if updates:
                    tx.set("monitorLimits", "searchapi", {**provider, **updates})
            if current.active_run_id != run.id:
                lost = run.model_copy(
                    update={
                        "status": "failed",
                        "error_code": "MONITOR_LEASE_LOST",
                        "completed_at": utc_now(),
                    }
                )
                tx.set("monitorRuns", run.id, serialize(lost))
                return False
            updated = current.model_copy(
                update={"lease_until": None, "active_run_id": None, "last_error": run.error_code}
            )
            tx.set("monitorSources", source.id, serialize(updated))
            tx.set("monitorRuns", run.id, serialize(run))
            return True

        if not self.store.atomic(finish):
            raise Conflict("A newer collection owns this source")

    def run(self, source_id: str, user: Principal):
        source, run = self._reserve(source_id, user)
        auto_item = None
        try:
            if source.kind == "instagram_ads":
                result = self.collector.fetch(
                    source,
                    before_search=lambda credits: self._authorize_provider_search(
                        source, run, credits
                    ),
                )
            else:
                result = self.collector.fetch(source)
            run.fetched = (
                result.fetched_count if result.fetched_count is not None else len(result.items)
            )
            run.limited, run.unreadable = result.limited, result.unreadable
            run.provider_credits_before = result.provider_credits_before
            for observation in result.items:
                item, created = self._ingest(source, run, observation, result)
                if item:
                    run.relevant += 1
                    run.created += int(created)
                    run.duplicates += int(not created)
                    if (
                        auto_item is None
                        and item.ai_status == "not_requested"
                        and item.status != "dismissed"
                    ):
                        auto_item = item
            # Opt-in, at most ONE paid analysis per source run, including duplicates
            # that have not yet been attempted. Existing global/user quotas also apply.
            if source.auto_analyze and auto_item:
                try:
                    analyzed = self.analyze(
                        auto_item.id,
                        ItemAnalyze(
                            expected_version=auto_item.version,
                            request_id=uuid5(NAMESPACE_URL, f"monitor:{run.id}:{auto_item.id}"),
                        ),
                        user,
                    )
                    run.auto_ai_status = analyzed.ai_status
                except AppError as error:
                    run.auto_ai_status = error.code
            run.status = "succeeded"
        except Exception as error:
            run.status = "failed"
            run.error_code = error.code if isinstance(error, AppError) else "MONITOR_RUN_FAILED"
            run.completed_at = utc_now()
            self._finish(source, run)
            if isinstance(error, AppError):
                raise
            raise AppError(
                502, "MONITOR_RUN_FAILED", "Collection failed; inspect source status"
            ) from None
        run.completed_at = utc_now()
        self._finish(source, run)
        return serialize(run)

    def run_due(self, user):
        results = []
        sources = [MonitorSource.model_validate(row) for row in self.sources()["items"]]
        # Oldest due first: a bounded batch must not starve later source IDs.
        sources.sort(key=lambda source: (source.next_run_at or source.created_at, source.id))
        for source in sources:
            if source.kind == "instagram_ads":
                if not (
                    self.settings.searchapi_schedule_enabled
                    and self.settings.searchapi_enabled
                    and self.settings.searchapi_api_key.get_secret_value()
                ):
                    continue
                quota = self.store.get("monitorLimits", f"searchapi-{utc_now():%Y%m%d}") or {}
                if quota.get("count", 0) >= self.settings.searchapi_daily_limit:
                    # Exhausted Meta quota must not starve unrelated public-source work.
                    continue
            if not source.enabled or (source.next_run_at and source.next_run_at > utc_now()):
                continue
            if len(results) >= self.settings.monitor_sources_per_tick:
                break
            try:
                results.append(self.run(source.id, user))
            except AppError as error:
                results.append({"sourceId": source.id, "errorCode": error.code})

        def heartbeat(tx):
            tx.set("monitorLimits", "worker", {"id": "worker", "lastTickAt": utc_now().isoformat()})

        self.store.atomic(heartbeat)
        return results

    def review(self, item_id: str, payload: ItemReview, user: Principal):
        def review(tx):
            item = self.item(item_id, tx)
            if item.version != payload.expected_version:
                raise Conflict()
            updated = item.model_copy(
                update={
                    "status": payload.decision,
                    "basis_review": item.basis_review if payload.decision == "dismissed" else None,
                    "notes": payload.notes,
                    "reviewer": user.uid,
                    "reviewed_at": utc_now(),
                    "version": item.version + 1,
                }
            )
            event = monitor_event(user, item.id, "item.review", serialize(payload))
            tx.set("monitorItems", item.id, serialize(updated))
            tx.create("monitorEvents", event["id"], event)
            return updated

        return self.store.atomic(review)

    def _registry_attempt(self):
        reserve_registry_read(self.store)

    def registry_search(self, item_id, query):
        self.item(item_id)
        if not 3 <= len(query.strip()) <= 100:
            raise AppError(422, "REGISTRY_QUERY_INVALID", "Enter the complex name or address")
        self._registry_attempt()
        return self.registry.search(query)

    def registry_detail(self, item_id, record_id):
        self.item(item_id)
        self._registry_attempt()
        return self.registry.detail(record_id)

    def confirm_basis(self, item_id, payload: ItemBasisReview, user):
        item = self.item(item_id)
        if item.version != payload.expected_version or item.ai_status == "running":
            raise Conflict()
        if item.advertisement_id:
            raise Conflict("Review legal basis in the linked complex instead")
        observed = item.created_at.astimezone(ZoneInfo("Asia/Qyzylorda")).date()
        published = (
            item.published_at.astimezone(ZoneInfo("Asia/Qyzylorda")).date()
            if item.published_at
            else None
        )
        if payload.advertisement_date > observed or (
            published and payload.advertisement_date != published
        ):
            raise AppError(422, "REGISTRY_DATE_MISMATCH", "Check the original advertisement date")
        self._registry_attempt()
        document = RegistryDocument.model_validate(self.registry.detail(payload.record_id))
        if document.document_sha256 != payload.expected_document_sha256:
            raise AppError(
                409, "REGISTRY_DOCUMENT_CHANGED", "Registry document changed; review again"
            )
        if document.issued_on > payload.advertisement_date:
            raise AppError(
                422, "REGISTRY_DOCUMENT_TOO_RECENT", "Document issued after advertisement"
            )
        proof = BasisReview(
            document=document,
            advertisement_date=payload.advertisement_date,
            reviewer=user.uid,
            reviewed_at=utc_now(),
            notes=payload.notes,
        )

        def save(tx):
            current = self.item(item_id, tx)
            if (
                current.version != payload.expected_version
                or current.ai_status == "running"
                or current.advertisement_id
            ):
                raise Conflict()
            updated = current.model_copy(
                update={
                    "basis_review": proof,
                    "status": "dismissed",
                    "reviewer": user.uid,
                    "reviewed_at": proof.reviewed_at,
                    "notes": payload.notes,
                    "version": current.version + 1,
                }
            )
            event = monitor_event(user, item_id, "item.basis.confirm", serialize(proof))
            tx.set("monitorItems", item_id, serialize(updated))
            tx.create("monitorEvents", event["id"], event)
            return updated

        return self.store.atomic(save)

    def analyze(self, item_id: str, payload: ItemAnalyze, user: Principal):
        self.client.check_config()
        from app.services.materials import MaterialService

        MaterialService(self.workspace).sync_legacy()
        now, request_id = utc_now(), str(payload.request_id)

        def reserve(tx):
            item = self.item(item_id, tx)
            existing = tx.get("monitorAiRuns", request_id)
            if existing:
                if existing["itemId"] != item_id or existing["actorUid"] != user.uid:
                    raise Conflict("Request ID already used")
                return item, False
            if item.version != payload.expected_version or item.ai_status == "running":
                raise Conflict()
            if item.advertisement_id:
                raise Conflict("Analyze the linked advertisement instead")
            updated = item.model_copy(
                update={
                    "ai_status": "running",
                    "ai_request_id": request_id,
                    "ai_error": None,
                    "ai_model": self.settings.gemini_model,
                    "ai_prompt_version": PROMPT_VERSION,
                    "version": item.version + 1,
                }
            )
            tx.set("monitorItems", item.id, serialize(updated))
            tx.create(
                "monitorAiRuns",
                request_id,
                {
                    "id": request_id,
                    "itemId": item_id,
                    "actorUid": user.uid,
                    "createdAt": now.isoformat(),
                    "status": "running",
                },
            )
            return updated, True

        item, reserved = self.store.atomic(reserve)
        if not reserved:
            return item
        result, error = None, None
        try:
            from app.services.material_provider import cached_extract

            result = cached_extract(
                self.workspace, self.settings, self.client, item.text, None, user, "public"
            )
        except Exception as failure:
            error = failure.code if isinstance(failure, AppError) else "AI_ANALYSIS_FAILED"

        def finish(tx):
            current = self.item(item_id, tx)
            run = self.require("monitorAiRuns", request_id, tx)
            if current.ai_request_id != request_id or run["status"] != "running":
                raise Conflict()
            updated = current.model_copy(
                update={
                    "extraction": result,
                    "ai_error": error,
                    "ai_status": "failed" if error else "succeeded",
                    "ai_completed_at": utc_now(),
                    "version": current.version + 1,
                }
            )
            event = monitor_event(
                user,
                item_id,
                "item.analyze",
                {"requestId": request_id, "status": updated.ai_status, "errorCode": error},
            )
            tx.set("monitorItems", item_id, serialize(updated))
            tx.set(
                "monitorAiRuns",
                request_id,
                {
                    **run,
                    "status": updated.ai_status,
                    "model": item.ai_model,
                    "promptVersion": item.ai_prompt_version,
                    "inputSha256": item.text_sha256,
                    "completedAt": utc_now().isoformat(),
                    "errorCode": error,
                    "extraction": serialize(result) if result else None,
                },
            )
            tx.create("monitorEvents", event["id"], event)
            return updated

        updated = self.store.atomic(finish)
        if error == "AI_DAILY_LIMIT":
            raise AppError(429, "AI_DAILY_LIMIT", "Daily analysis limit reached")
        return updated

    def attach(self, item_id: str, payload: ItemAttach, user: Principal):
        if self.workspace.demo_only:
            raise AppError(
                409,
                "MONITOR_LIVE_REGISTRY_REQUIRED",
                "Real publications cannot be linked to a DEMO registry",
            )

        def attach(tx):
            item = self.item(item_id, tx)
            complex_ = self.workspace.complex(payload.complex_id, tx)
            if complex_.demo:
                raise AppError(
                    422, "SCOPE_MISMATCH", "Do not link a real publication to a fictional complex"
                )
            if item.advertisement_id:
                ad = self.workspace.require_record("advertisements", item.advertisement_id, tx)
                if ad["complexId"] != complex_.id:
                    raise Conflict("Already linked to another complex")
                return {"advertisementId": item.advertisement_id}
            if item.version != payload.expected_version or item.ai_status == "running":
                raise Conflict()
            ad = Advertisement(
                id=uuid4().hex,
                complex_id=complex_.id,
                platform={
                    "telegram_post": "Telegram",
                    "instagram_ad": "Instagram (Meta Ad Library)",
                }.get(item.content_kind, "Web search (snippet)"),
                account=item.account or "Unknown",
                source_url=item.original_url,
                text=item.text,
                published_at=item.published_at,
                captured_at=item.created_at,
                created_by=user.uid,
                demo=False,
            )
            event = audit_event(
                user,
                "advertisement",
                ad.id,
                "monitor.attach",
                complex_,
                {"monitorItemId": item.id, "notes": payload.notes},
            )
            evidence, hypotheses = [], []
            run_id = uuid4().hex
            if item.ai_status == "succeeded" and item.extraction:
                for proposal in item.extraction.hypotheses:
                    e = Evidence(
                        id=uuid4().hex,
                        complex_id=complex_.id,
                        advertisement_id=ad.id,
                        type="advertisement",
                        source_url=ad.source_url,
                        source_reference=(
                            f"AI hypothesis; {item.ai_prompt_version}; unverified; "
                            f"monitor:{item.id}"
                        ),
                        excerpt=proposal.quote,
                        captured_at=item.created_at,
                        status="proposed",
                        demo=False,
                    )
                    evidence.append(e)
                    hypotheses.append(
                        Hypothesis(
                            id=uuid4().hex,
                            **proposal.model_dump(),
                            run_id=run_id,
                            complex_id=complex_.id,
                            advertisement_id=ad.id,
                            evidence_id=e.id,
                            model=item.ai_model,
                            prompt_version=item.ai_prompt_version,
                            input_sha256=item.text_sha256,
                            created_at=item.ai_completed_at or utc_now(),
                            demo=False,
                        )
                    )
            tx.create("advertisements", ad.id, serialize(ad))
            tx.create("auditLogs", event.id, serialize(event))
            for e in evidence:
                tx.create("evidence", e.id, serialize(e))
            for h in hypotheses:
                tx.create("aiHypotheses", h.id, serialize(h))
            if item.ai_status == "succeeded" and item.extraction:
                tx.create(
                    "analysisRuns",
                    run_id,
                    {
                        "id": run_id,
                        "advertisementId": ad.id,
                        "complexId": complex_.id,
                        "createdBy": user.uid,
                        "createdAt": utc_now().isoformat(),
                        "demo": False,
                        "fingerprint": sha(f"{ad.id}:1:None"),
                        "status": "succeeded",
                        "model": item.ai_model,
                        "promptVersion": item.ai_prompt_version,
                        "hypothesisIds": [h.id for h in hypotheses],
                        "screenshotId": None,
                        "inputSha256": item.text_sha256,
                        "extraction": serialize(item.extraction),
                        "completedAt": item.ai_completed_at.isoformat(),
                        "monitorItemId": item.id,
                    },
                )
            tx.set(
                "monitorItems",
                item_id,
                serialize(
                    item.model_copy(update={"advertisement_id": ad.id, "version": item.version + 1})
                ),
            )
            return {"advertisementId": ad.id}

        return self.store.atomic(attach)
