from uuid import uuid4

from pydantic import ValidationError

from app.core.errors import AppError, Conflict, NotFound
from app.models.audit import AuditEvent
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.entities import Advertisement, Complex, Developer, Evidence, LegalBasis
from app.models.risk import RiskFactor, RiskZone
from app.repositories.store import Store, UnitOfWork
from app.schemas.workspace import (
    AdvertisementCreate,
    ComplexCreate,
    EvidenceCreate,
    EvidenceReview,
    FactorDecision,
    LegalBasisUpdate,
)
from app.services.evidence import validate_factor_evidence
from app.services.risk import calculate_risk


def serialize(model) -> dict:
    return model.model_dump(mode="json", by_alias=True)


def audit_event(
    user: Principal,
    entity_type: str,
    entity_id: str,
    action: str,
    complex_: Complex,
    details: dict | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=uuid4().hex,
        entity_type=entity_type,
        entity_id=entity_id,
        complex_id=complex_.id,
        action=action,
        actor_uid=user.uid,
        created_at=utc_now(),
        demo=complex_.demo,
        details=details or {},
    )


class WorkspaceService:
    def __init__(self, store: Store, *, demo_only: bool = True):
        self.store = store
        self.demo_only = demo_only

    def require_record(self, collection: str, record_id: str, tx: UnitOfWork | None = None) -> dict:
        row = (tx or self.store).get(collection, record_id)
        if row is None or (self.demo_only and row.get("demo") is not True):
            raise NotFound()
        return row

    def complex(self, record_id: str, tx: UnitOfWork | None = None) -> Complex:
        return Complex.model_validate(self.require_record("complexes", record_id, tx))

    def project_company(
        self, complex_: Complex, role: str, tx: UnitOfWork | None = None
    ) -> Developer | None:
        company_id = (
            complex_.developer_id if role == "developer" else complex_.authorized_company_id
        )
        if not company_id:
            return None
        legacy = Developer.model_validate(self.require_record("developers", company_id, tx))
        party = next(
            (p for p in complex_.party_snapshots if p.role == role and p.company_id == company_id),
            None,
        )
        if party:
            return Developer(
                id=party.company_id, name=party.name, bin=party.bin, demo=complex_.demo
            )
        return legacy

    def complex_detail(self, record_id: str) -> dict:
        complex_ = self.complex(record_id)
        developer = self.project_company(complex_, "developer")
        authorized = self.project_company(complex_, "authorized_company")
        return {
            **serialize(complex_),
            "developer": serialize(developer),
            "authorizedCompany": serialize(authorized) if authorized else None,
            "risk": serialize(calculate_risk(complex_.factors)),
            "reviewPriority": self.material_priority(record_id),
        }

    def material_priority(self, record_id):
        from app.services.materials import MaterialService

        return MaterialService(self).priority_for_complex(record_id)

    def list_complexes(
        self,
        *,
        q: str = "",
        city: str | None = None,
        zone: RiskZone | None = None,
        sort: str = "risk",
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        # Bounded catalog scan supports substring search for the small DEMO corpus.
        # The response explicitly reports its bound; there is no silent full-registry claim.
        filters = [("demo", "==", True)] if self.demo_only else []
        if city:
            filters.append(("city", "==", city))
        raw = self.store.list("complexes", filters=filters, limit=500)
        rows = []
        for row in raw:
            complex_ = Complex.model_validate(row)
            if q.casefold() not in f"{complex_.name} {complex_.city} {complex_.address}".casefold():
                continue
            risk = calculate_risk(complex_.factors)
            if zone and risk.zone != zone:
                continue
            rows.append({**serialize(complex_), "risk": serialize(risk)})
        from app.services.materials import MaterialService

        priorities = MaterialService(self).priorities_for_complexes()
        for row in rows:
            row["reviewPriority"] = priorities.get(
                row["id"],
                {
                    "score": None,
                    "level": "unknown",
                    "reasons": ["Нет завершённого анализа материалов."],
                },
            )
        if sort == "priority":
            rows.sort(
                key=lambda row: (
                    -(
                        row["reviewPriority"]["score"]
                        if row["reviewPriority"]["score"] is not None
                        else -1
                    ),
                    row["id"],
                )
            )
        elif sort == "risk":
            rows.sort(key=lambda row: (-row["risk"]["score"], row["id"]))
        else:
            rows.sort(key=lambda row: (row["name"].casefold(), row["id"]))
        next_offset = offset + limit
        return {
            "items": rows[offset:next_offset],
            "total": len(rows),
            "nextCursor": str(next_offset) if next_offset < len(rows) else None,
            "catalogLimited": len(raw) == 500,
        }

    def page(
        self,
        collection: str,
        *,
        complex_id: str | None = None,
        after_id: str | None = None,
        limit: int = 50,
        extra_filters=None,
    ) -> dict:
        filters = [("demo", "==", True)] if self.demo_only else []
        if complex_id:
            self.complex(complex_id)
            filters.append(("complexId", "==", complex_id))
        filters.extend(extra_filters or [])
        rows = self.store.list(
            collection,
            filters=filters,
            after_id=after_id,
            limit=limit + 1,
            newest_first=collection == "auditLogs",
        )
        has_more = len(rows) > limit
        return {"items": rows[:limit], "nextCursor": rows[limit - 1]["id"] if has_more else None}

    def create_complex(self, payload: ComplexCreate, user: Principal) -> dict:
        now = utc_now()
        complex_ = Complex(id=uuid4().hex, **payload.model_dump(), created_at=now, updated_at=now)
        event = audit_event(user, "complex", complex_.id, "complex.create", complex_)

        def operation(tx):
            developer = self.require_record("developers", payload.developer_id, tx)
            if developer.get("demo") != complex_.demo:
                raise AppError(422, "SCOPE_MISMATCH", "Developer and complex scopes must match")
            tx.create("complexes", complex_.id, serialize(complex_))
            tx.create("auditLogs", event.id, serialize(event))

        self.store.atomic(operation)
        return {**serialize(complex_), "risk": serialize(calculate_risk(complex_.factors))}

    def create_advertisement(self, payload: AdvertisementCreate, user: Principal) -> Advertisement:
        record_id = uuid4().hex

        def operation(tx):
            complex_ = self.complex(payload.complex_id, tx)
            ad = Advertisement(
                id=record_id,
                **payload.model_dump(),
                captured_at=utc_now(),
                created_by=user.uid,
                demo=complex_.demo,
            )
            event = audit_event(user, "advertisement", ad.id, "advertisement.create", complex_)
            from app.services.material_projection import ad_occurrence, stage_occurrence

            stage_occurrence(tx, ad_occurrence(tx, ad))
            tx.create("advertisements", ad.id, serialize(ad))
            tx.create("auditLogs", event.id, serialize(event))
            return ad

        return self.store.atomic(operation)

    def create_evidence(self, payload: EvidenceCreate, user: Principal) -> Evidence:
        record_id = uuid4().hex

        def operation(tx):
            complex_ = self.complex(payload.complex_id, tx)
            source_url = payload.source_url
            if payload.advertisement_id:
                ad = self.require_record("advertisements", payload.advertisement_id, tx)
                if ad["complexId"] != complex_.id:
                    raise AppError(
                        422, "EVIDENCE_MISMATCH", "Advertisement belongs to another complex"
                    )
                if payload.type == "advertisement" and payload.excerpt not in ad["text"]:
                    raise AppError(422, "EXCERPT_MISMATCH", "Quote must occur in the original text")
                if payload.type == "advertisement":
                    if source_url and str(source_url) != ad["sourceUrl"]:
                        raise AppError(422, "SOURCE_MISMATCH", "Source must match the original ad")
                    source_url = ad["sourceUrl"]
            item = Evidence(
                id=record_id,
                **payload.model_dump(exclude={"source_url"}),
                source_url=source_url,
                demo=complex_.demo,
            )
            event = audit_event(user, "evidence", item.id, "evidence.create", complex_)
            tx.create("evidence", item.id, serialize(item))
            tx.create("auditLogs", event.id, serialize(event))
            return item

        return self.store.atomic(operation)

    def review_evidence(self, record_id: str, payload: EvidenceReview, user: Principal) -> Evidence:
        def operation(tx):
            original = Evidence.model_validate(self.require_record("evidence", record_id, tx))
            if original.version != payload.expected_version:
                raise Conflict()
            complex_ = self.complex(original.complex_id, tx)
            # Reviewed evidence is immutable once linked to a confirmed factor. Changes require
            # explicitly unconfirming that factor first, preserving the score invariant.
            if any(
                record_id in factor.evidence_ids and factor.status == "confirmed"
                for factor in complex_.factors
            ):
                raise Conflict("Evidence supports a confirmed factor; review that factor first")
            changes = payload.model_dump(exclude={"decision", "notes", "expected_version"})
            try:
                reviewed = Evidence.model_validate(
                    {
                        **original.model_dump(),
                        **changes,
                        "status": payload.decision,
                        "reviewer": user.uid,
                        "reviewed_at": utc_now(),
                        "version": original.version + 1,
                    }
                )
            except ValidationError:
                raise AppError(
                    422, "INVALID_EVIDENCE", "Evidence source or review is incomplete"
                ) from None
            event = audit_event(
                user,
                "evidence",
                record_id,
                "evidence.review",
                complex_,
                {"from": original.status, "to": reviewed.status, "notes": payload.notes},
            )
            tx.set("evidence", record_id, serialize(reviewed))
            tx.create("auditLogs", event.id, serialize(event))
            return reviewed

        return self.store.atomic(operation)

    def factor_decision(self, complex_id: str, payload: FactorDecision, user: Principal) -> dict:
        def operation(tx):
            complex_ = self.complex(complex_id, tx)
            if complex_.version != payload.expected_version:
                raise Conflict()
            evidence = [
                Evidence.model_validate(self.require_record("evidence", eid, tx))
                for eid in payload.evidence_ids
            ]
            if any(item.complex_id != complex_id for item in evidence):
                raise AppError(422, "EVIDENCE_MISMATCH", "Evidence belongs to another complex")
            if payload.decision == "confirmed":
                try:
                    validate_factor_evidence(payload.code, complex_, evidence)
                except ValueError as exc:
                    raise AppError(422, "FACTOR_NOT_SUPPORTED", str(exc)) from None
            old_risk = calculate_risk(complex_.factors)
            try:
                factor = RiskFactor(
                    code=payload.code,
                    status=payload.decision,
                    evidence_ids=payload.evidence_ids,
                    reviewer=user.uid,
                    reviewed_at=utc_now(),
                    notes=payload.notes,
                )
            except ValidationError:
                raise AppError(
                    422, "INVALID_FACTOR", "Factor evidence references are invalid"
                ) from None
            factors = [item for item in complex_.factors if item.code != payload.code] + [factor]
            updated = Complex.model_validate(
                {
                    **complex_.model_dump(),
                    "factors": factors,
                    "version": complex_.version + 1,
                    "updated_at": utc_now(),
                }
            )
            risk = calculate_risk(updated.factors)
            event = audit_event(
                user,
                "complex",
                complex_id,
                "factor.review",
                updated,
                {
                    "code": payload.code,
                    "decision": payload.decision,
                    "beforeScore": old_risk.score,
                    "afterScore": risk.score,
                    "evidenceIds": payload.evidence_ids,
                    "notes": payload.notes,
                },
            )
            tx.set("complexes", complex_id, serialize(updated))
            tx.create("auditLogs", event.id, serialize(event))
            return {**serialize(updated), "risk": serialize(risk)}

        return self.store.atomic(operation)

    def update_basis(self, complex_id: str, payload: LegalBasisUpdate, user: Principal) -> dict:
        def operation(tx):
            complex_ = self.complex(complex_id, tx)
            if complex_.version != payload.expected_version:
                raise Conflict()
            try:
                basis = LegalBasis.model_validate(
                    {**payload.basis.model_dump(), "reviewer": user.uid, "checked_at": utc_now()}
                )
            except ValidationError:
                raise AppError(
                    422, "INVALID_BASIS", "Reviewed basis needs type, source and reference"
                ) from None
            if basis.status == "confirmed" and basis.valid_until and basis.valid_until < utc_now():
                raise AppError(422, "EXPIRED_BASIS", "Cannot confirm an expired applicable basis")
            try:
                updated = Complex.model_validate(
                    {
                        **complex_.model_dump(),
                        "legal_basis": basis,
                        "version": complex_.version + 1,
                        "updated_at": utc_now(),
                    }
                )
            except ValidationError:
                raise Conflict(
                    "Review confirmed R1 before confirming an applicable legal basis"
                ) from None
            event = audit_event(
                user,
                "complex",
                complex_id,
                "basis.review",
                updated,
                {"from": serialize(complex_.legal_basis), "to": serialize(basis)},
            )
            tx.set("complexes", complex_id, serialize(updated))
            tx.create("auditLogs", event.id, serialize(event))
            return {**serialize(updated), "risk": serialize(calculate_risk(updated.factors))}

        return self.store.atomic(operation)
