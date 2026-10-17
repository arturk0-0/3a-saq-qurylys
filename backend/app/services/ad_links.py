"""Human-reviewed advertising matches, isolated from legal evidence and risk factors."""

import hashlib
import json
from dataclasses import asdict

from app.core.errors import AppError, Conflict
from app.models.ad_trace import AdLink, TraceDecision, TraceSave, TraceSnapshot
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.entities import Advertisement
from app.services.ad_trace import TRACE_VERSION, TraceDocument, propose_links
from app.services.workspace import WorkspaceService, audit_event, serialize


def document(ad: Advertisement) -> TraceDocument:
    return TraceDocument(ad.id, ad.text, ad.version, ad.demo)


def snapshot(a: Advertisement, b: Advertisement, names: list[str]) -> TraceSnapshot:
    result = propose_links([document(a), document(b)], known_names=names)
    if result.identifiers_limited:
        raise AppError(
            422, "TRACE_TOO_MANY_IDENTIFIERS", "Narrow the source before reviewing a match"
        )
    if not result.proposals:
        raise AppError(422, "TRACE_NO_MATCH", "No supported shared identifier")
    return TraceSnapshot(**asdict(result.proposals[0]), normalizer_version=TRACE_VERSION)


def snapshot_id(value: TraceSnapshot) -> str:
    # Includes reasons as well as original sources; a changed alias catalog cannot
    # overwrite a reviewed snapshot with different reasons under the same ID.
    canonical = json.dumps(
        serialize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class AdLinksService:
    def __init__(self, workspace: WorkspaceService):
        self.workspace = workspace
        self.store = workspace.store

    def ad(self, record_id, tx=None):
        return Advertisement.model_validate(
            self.workspace.require_record("advertisements", record_id, tx)
        )

    def candidates(self, record_id: str) -> dict:
        anchor = self.ad(record_id)
        complex_ = self.workspace.complex(anchor.complex_id)
        names = [complex_.name, *complex_.aliases]
        rows = self.store.list("advertisements", filters=[("demo", "==", anchor.demo)], limit=201)
        peers = [self.ad_from_row(row) for row in rows if row["id"] != anchor.id]
        items = []
        incomplete = False
        for peer in peers[:199]:
            result = propose_links([document(anchor), document(peer)], known_names=names)
            incomplete |= result.identifiers_limited
            if not result.proposals or result.identifiers_limited:
                continue
            proposed = TraceSnapshot(
                **asdict(result.proposals[0]), normalizer_version=TRACE_VERSION
            )
            items.append((peer, proposed))
        response = []
        for peer, proposed in items[:20]:
            link_id = snapshot_id(proposed)
            existing = self.store.get("adLinks", link_id)
            saved = None
            if existing:
                saved = AdLink.model_validate(existing)
                if saved.demo != anchor.demo:
                    raise AppError(422, "SCOPE_MISMATCH", "Scopes must match")
            response.append(
                {
                    "id": link_id,
                    "snapshot": serialize(proposed),
                    "otherAdvertisement": {
                        "id": peer.id,
                        "complexId": peer.complex_id,
                        "platform": peer.platform,
                        "account": peer.account,
                        "sourceUrl": str(peer.source_url),
                        "version": peer.version,
                    },
                    "saved": serialize(saved) if saved else None,
                }
            )
        return {
            "items": response,
            "scannedCount": min(len(peers), 199),
            "scanLimited": len(peers) > 199,
            "resultsLimited": len(items) > 20,
            "identifiersLimited": incomplete,
            "normalizerVersion": TRACE_VERSION,
        }

    @staticmethod
    def ad_from_row(row):
        return Advertisement.model_validate(row)

    def save(self, record_id: str, payload: TraceSave, user: Principal) -> AdLink:
        def operation(tx):
            a, b = self.ad(record_id, tx), self.ad(payload.other_advertisement_id, tx)
            if a.id == b.id:
                raise AppError(422, "TRACE_SELF_LINK", "Choose two different advertisements")
            if a.version != payload.expected_version or b.version != payload.expected_other_version:
                raise Conflict()
            complexes = {ad.complex_id: self.workspace.complex(ad.complex_id, tx) for ad in (a, b)}
            if a.demo != b.demo or any(c.demo != a.demo for c in complexes.values()):
                raise AppError(422, "SCOPE_MISMATCH", "Scopes must match")
            # Use the same anchor catalog as the preview. Names are saved as reasons;
            # later review validates against originals, never a changed alias catalog.
            complex_ = complexes[a.complex_id]
            value = snapshot(a, b, [complex_.name, *complex_.aliases])
            link_id = snapshot_id(value)
            if link_id != payload.expected_snapshot_id:
                raise Conflict("Match reasons changed; rescan before saving")
            existing = tx.get("adLinks", link_id)
            if existing:
                return AdLink.model_validate(existing)
            saved = AdLink(
                **value.model_dump(), id=link_id, created_by=user.uid, created_at=utc_now()
            )
            events = [
                audit_event(user, "adLink", saved.id, "adLink.propose", c)
                for c in complexes.values()
            ]
            tx.create("adLinks", saved.id, serialize(saved))
            for event in events:
                tx.create("auditLogs", event.id, serialize(event))
            return saved

        return self.store.atomic(operation)

    def decide(self, link_id: str, payload: TraceDecision, user: Principal) -> AdLink:
        def operation(tx):
            saved = AdLink.model_validate(self.workspace.require_record("adLinks", link_id, tx))
            a, b = self.ad(saved.left_id, tx), self.ad(saved.right_id, tx)
            complexes = {ad.complex_id: self.workspace.complex(ad.complex_id, tx) for ad in (a, b)}
            if any(ad.demo != saved.demo for ad in (a, b)) or any(
                c.demo != saved.demo for c in complexes.values()
            ):
                raise AppError(422, "SCOPE_MISMATCH", "Scopes must match")
            if saved.version != payload.expected_version or saved.status != "proposed":
                raise Conflict()
            if (
                a.version != saved.left_version
                or b.version != saved.right_version
                or hashlib.sha256(a.text.encode()).hexdigest() != saved.left_text_sha256
                or hashlib.sha256(b.text.encode()).hexdigest() != saved.right_text_sha256
                or saved.normalizer_version != TRACE_VERSION
            ):
                raise AppError(409, "TRACE_STALE", "Source snapshot changed; rescan advertisements")
            updated = saved.model_copy(
                update={
                    "status": payload.decision,
                    "notes": payload.notes,
                    "reviewer": user.uid,
                    "reviewed_at": utc_now(),
                    "version": saved.version + 1,
                }
            )
            events = [
                audit_event(
                    user,
                    "adLink",
                    saved.id,
                    "adLink.review",
                    c,
                    {
                        "decision": payload.decision,
                        "linkVersion": updated.version,
                        "notes": payload.notes,
                    },
                )
                for c in complexes.values()
            ]
            tx.set("adLinks", saved.id, serialize(updated))
            for event in events:
                tx.create("auditLogs", event.id, serialize(event))
            return updated

        return self.store.atomic(operation)
