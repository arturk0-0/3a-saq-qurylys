import json
from uuid import uuid4

from app.core.errors import AppError, Conflict
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.entities import Developer, Evidence
from app.models.signals import (
    EvidenceSnapshot,
    Signal,
    SignalCreate,
    SignalDecision,
    SignalSnapshot,
)
from app.services.evidence import validate_factor_evidence
from app.services.risk import calculate_risk
from app.services.workspace import WorkspaceService, audit_event, serialize


class SignalService:
    def __init__(self, workspace: WorkspaceService):
        self.workspace = workspace

    def snapshot(self, complex_id, tx) -> SignalSnapshot:
        complex_ = self.workspace.complex(complex_id, tx)
        developer = Developer.model_validate(
            self.workspace.require_record("developers", complex_.developer_id, tx)
        )
        factors = [f for f in complex_.factors if f.status == "confirmed"]
        ids = sorted({eid for f in factors for eid in f.evidence_ids})
        evidence = {
            eid: Evidence.model_validate(self.workspace.require_record("evidence", eid, tx))
            for eid in ids
        }
        for factor in factors:
            try:
                validate_factor_evidence(
                    factor.code, complex_, [evidence[eid] for eid in factor.evidence_ids]
                )
            except ValueError:
                raise Conflict("Confirmed factors need a new evidence review") from None
        snapshot = SignalSnapshot(
            complex=complex_,
            developer=developer,
            risk=calculate_risk(complex_.factors),
            captured_at=utc_now(),
            evidence=[
                EvidenceSnapshot(
                    id=item.id,
                    type=item.type,
                    source_url=str(item.source_url) if item.source_url else None,
                    source_reference=item.source_reference,
                    excerpt=item.excerpt[:2000],
                    excerpt_truncated=len(item.excerpt) > 2000,
                    captured_at=item.captured_at,
                    reviewer=item.reviewer,
                    reviewed_at=item.reviewed_at,
                    sha256=item.sha256,
                    version=item.version,
                )
                for item in evidence.values()
            ],
        )
        if len(json.dumps(serialize(snapshot), ensure_ascii=False).encode()) > 250_000:
            raise AppError(422, "REPORT_TOO_LARGE", "Evidence snapshot exceeds the report limit")
        return snapshot

    def create(self, payload: SignalCreate, user: Principal) -> Signal:
        record_id = uuid4().hex

        def operation(tx):
            snapshot = self.snapshot(payload.complex_id, tx)
            if snapshot.complex.version != payload.expected_complex_version:
                raise Conflict()
            now = utc_now()
            signal = Signal(
                id=record_id,
                **payload.model_dump(exclude={"expected_complex_version"}),
                snapshot=snapshot,
                created_by=user.uid,
                created_at=now,
                updated_at=now,
                demo=snapshot.complex.demo,
            )
            event = audit_event(
                user,
                "signal",
                record_id,
                "signal.create",
                snapshot.complex,
                {"notes": payload.reason},
            )
            tx.create("signals", record_id, serialize(signal))
            tx.create("signalRevisions", f"{record_id}-1", serialize(signal))
            tx.create("auditLogs", event.id, serialize(event))
            return signal

        return self.workspace.store.atomic(operation)

    def get(self, record_id: str) -> Signal:
        return Signal.model_validate(self.workspace.require_record("signals", record_id))

    def decision(self, record_id: str, payload: SignalDecision, user: Principal) -> Signal:
        def operation(tx):
            signal = Signal.model_validate(self.workspace.require_record("signals", record_id, tx))
            complex_ = self.workspace.complex(signal.complex_id, tx)
            if signal.version != payload.expected_version:
                raise Conflict()
            transitions = {
                ("draft", "submit"): "pending_review",
                ("returned", "submit"): "pending_review",
                ("pending_review", "confirm"): "confirmed",
                ("pending_review", "return"): "returned",
            }
            target = transitions.get((signal.status, payload.action))
            if target is None:
                raise Conflict("This signal transition is not allowed")
            if payload.action == "confirm" and complex_.version != signal.snapshot.complex.version:
                raise Conflict(
                    "Complex changed; return and resubmit the signal with a new snapshot"
                )
            if payload.action == "submit":
                signal.snapshot = self.snapshot(signal.complex_id, tx)
                signal.reviewer, signal.reviewed_at = None, None
            else:
                signal.reviewer, signal.reviewed_at = user.uid, utc_now()
            previous = signal.status
            signal.status, signal.review_notes = target, payload.notes
            signal.version += 1
            signal.updated_at = utc_now()
            event = audit_event(
                user,
                "signal",
                record_id,
                "signal.review",
                complex_,
                {
                    "from": previous,
                    "to": target,
                    "notes": payload.notes,
                    "signalVersion": signal.version,
                },
            )
            tx.set("signals", record_id, serialize(signal))
            tx.create("signalRevisions", f"{record_id}-{signal.version}", serialize(signal))
            tx.create("auditLogs", event.id, serialize(event))
            return signal

        return self.workspace.store.atomic(operation)
