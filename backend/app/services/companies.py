"""Source-attributed companies. Never edits confirmed risk, permits or existing complexes."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from pydantic import ValidationError

from app.core.errors import AppError, Conflict, NotFound
from app.models.common import utc_now
from app.models.companies import CompanyFact, CompanyRecord, RefreshCompany, SaveSourceProject
from app.models.entities import Complex, Developer
from app.models.provenance import PartySnapshot
from app.services.company_directory import CompanyDirectory
from app.services.company_sources import CompanyRegistry
from app.services.registries import normalized
from app.services.registry_usage import reserve_registry_read
from app.services.workspace import WorkspaceService, serialize


def company_id(bin_):
    return "bin-" + bin_


def project_id(record_id):
    return "homeportal-" + record_id


def public_profile(record):
    result = serialize(record)
    completed = {
        (p.commissioning_reference, p.commissioning_date, normalized(p.address))
        for p in record.projects
        if p.commissioning_reference
    }
    result["foundCompletedCount"] = len(completed) if completed else None
    result["coverage"] = "saved_source_projects_only"
    return result


class CompanyService:
    def __init__(self, workspace: WorkspaceService, registry: CompanyRegistry | None = None):
        self.workspace, self.store = workspace, workspace.store
        self.registry = registry or CompanyRegistry()

    def list(self, cursor=None, limit=20):
        rows = self.store.list("companies", after_id=cursor, limit=limit + 1)
        return {
            "items": [
                {"id": r["id"], "name": r["name"], "bin": r["bin"], "updatedAt": r["updatedAt"]}
                for r in rows[:limit]
            ],
            "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def get(self, record_id):
        row = self.store.get("companies", record_id)
        if row:
            return public_profile(CompanyRecord.model_validate(row))
        # Historical/DEMO developer IDs retain a functional page without fake public citations.
        legacy = self.workspace.require_record("developers", record_id)
        developer = Developer.model_validate(legacy)
        return {
            **serialize(developer),
            "facts": [],
            "projects": [],
            "version": 0,
            "updatedAt": None,
            "lastError": None,
            "foundCompletedCount": None,
            "coverage": "legacy_internal_record",
        }

    def search(self, query):
        if not 3 <= len(query.strip()) <= 100:
            raise AppError(422, "REGISTRY_QUERY_INVALID", "Enter a project name or address")
        reserve_registry_read(self.store)
        rows, limited = self.registry.client.home_search(query.strip())
        return {"items": rows, "limited": limited, "checkedAt": utc_now().isoformat()}

    def fetch(self, record_id):
        reserve_registry_read(self.store)
        return self.registry.project(record_id)

    def preview(self, record_id):
        project = self.fetch(record_id)
        saved = self.store.get("companyProjects", project_id(record_id))
        return {
            "project": serialize(project),
            "savedVersion": saved["version"] if saved else 0,
            "canImportToRegistry": not self.workspace.demo_only,
        }

    def _event(self, user, entity_id, action, details, complex_id=None):
        return dict(
            id=uuid4().hex,
            entityType="company",
            entityId=entity_id,
            complexId=complex_id,
            action=action,
            actorUid=user.uid,
            createdAt=utc_now().isoformat(),
            demo=False,
            details=details,
        )

    def directory_fact(self, bin_):
        try:
            reserve_registry_read(self.store)
            return CompanyDirectory(self.registry.client).registration(bin_), None
        except AppError as error:
            return None, error.code

    def _company(self, previous, bin_, projects, extra_facts=()):
        record = (
            CompanyRecord.model_validate(previous)
            if previous
            else CompanyRecord(
                id=company_id(bin_),
                bin=bin_,
                name=next(p.name for s in projects for p in s.parties if p.bin == bin_),
                updated_at=utc_now(),
            )
        )
        facts = list(record.facts)
        known = {(fact.field, fact.value, str(fact.source.url)): i for i, fact in enumerate(facts)}
        portfolio = {p.record_id: p for p in record.projects}
        for project in projects:
            matching = [p for p in project.parties if p.bin == bin_]
            if not matching:
                continue
            portfolio[project.record_id] = project
            for party in matching:
                values = {"name": party.name, "bin": bin_}
                if party.website:
                    values["website"] = str(party.website)
                for field, value in values.items():
                    fact = CompanyFact(field=field, value=value, source=project.source)
                    key = field, value, str(project.source.url)
                    if key in known:
                        facts[known[key]] = fact
                    else:
                        known[key] = len(facts)
                        facts.append(fact)
        for fact in extra_facts:
            key = fact.field, fact.value, str(fact.source.url)
            if key in known:
                facts[known[key]] = fact
            else:
                known[key] = len(facts)
                facts.append(fact)
        try:
            # Keep conflicting observations; never silently select/merge different BINs.
            return CompanyRecord.model_validate(
                {
                    **serialize(record),
                    "facts": [serialize(f) for f in facts],
                    "projects": [serialize(p) for p in portfolio.values()],
                    "updatedAt": utc_now(),
                    "lastAttemptAt": utc_now(),
                    "lastError": None,
                    "version": record.version + 1 if previous else 1,
                }
            )
        except ValidationError:
            raise AppError(409, "COMPANY_RECORD_LIMIT", "Source history limit reached") from None

    def save(self, record_id, payload: SaveSourceProject, user):
        if payload.import_to_registry and self.workspace.demo_only:
            raise AppError(403, "COMPANY_LIVE_REGISTRY_REQUIRED", "Real registry is disabled")
        project = self.fetch(record_id)
        if project.document_sha256 != payload.expected_document_sha256:
            raise AppError(409, "REGISTRY_DOCUMENT_CHANGED", "Source record changed; review again")
        developer = next((p for p in project.parties if p.role == "developer"), None)
        authorized = next((p for p in project.parties if p.role == "authorized_company"), None)
        if payload.import_to_registry and (not developer or not project.stage):
            raise AppError(422, "COMPANY_PROJECT_INCOMPLETE", "Project stage/developer is unknown")
        key = project_id(record_id)
        bins = sorted({p.bin for p in project.parties})
        # One optional secondary lookup per unique BIN, never inside a retried transaction.
        with ThreadPoolExecutor(max_workers=2) as pool:
            directory = dict(zip(bins, pool.map(self.directory_fact, bins), strict=True))

        def save(tx):
            old = tx.get("companyProjects", key)
            companies = {bin_: tx.get("companies", company_id(bin_)) for bin_ in bins}
            existing = tx.get("complexes", key) if payload.import_to_registry else None
            legacy = (
                {bin_: tx.get("developers", company_id(bin_)) for bin_ in bins}
                if payload.import_to_registry
                else {}
            )
            if (old["version"] if old else 0) != payload.expected_version:
                raise Conflict()
            records = {}
            for bin_ in bins:
                fact, error = directory[bin_]
                record = self._company(companies[bin_], bin_, [project], [fact] if fact else [])
                record.last_error = error
                records[bin_] = record
            complex_ = None
            if payload.import_to_registry:
                if existing:
                    # Never overwrite reviewed facts/coordinates/participants with a refresh.
                    raise Conflict("A registry card already exists; it was not overwritten")
                if any(row and row.get("demo") is not False for row in legacy.values()):
                    raise Conflict("Real and demo company scopes cannot be mixed")
                complex_ = Complex(
                    id=key,
                    name=project.name,
                    city=project.city,
                    address=project.address,
                    developer_id=company_id(developer.bin),
                    authorized_company_id=company_id(authorized.bin) if authorized else None,
                    participant_source=project.source,
                    party_snapshots=[
                        PartySnapshot(
                            company_id=company_id(p.bin),
                            name=p.name,
                            bin=p.bin,
                            role=p.role,
                            source=project.source,
                        )
                        for p in project.parties
                    ],
                    coordinates=project.coordinates,
                    coordinate_source=project.source if project.coordinates else None,
                    coordinate_status=project.coordinate_status,
                    stage=project.stage,
                    demo=False,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            for bin_, record in records.items():
                tx.set("companies", company_id(bin_), serialize(record))
                if complex_ and legacy[bin_] is None:
                    party = next(p for p in project.parties if p.bin == bin_)
                    tx.create(
                        "developers",
                        company_id(bin_),
                        serialize(
                            Developer(id=company_id(bin_), name=party.name, bin=bin_, demo=False)
                        ),
                    )
            tx.set(
                "companyProjects",
                key,
                {
                    "id": key,
                    "version": payload.expected_version + 1,
                    "project": serialize(project),
                    "demo": False,
                },
            )
            if complex_:
                tx.create("complexes", key, serialize(complex_))
            event = self._event(
                user,
                key,
                "company.project.save",
                {"project": serialize(project), "registryCreated": bool(complex_)},
                key if complex_ else None,
            )
            tx.create("auditLogs", event["id"], event)
            return {
                "companyIds": [company_id(bin_) for bin_ in bins],
                "registryId": key if complex_ else None,
                "savedVersion": payload.expected_version + 1,
            }

        return self.store.atomic(save)

    def refresh(self, record_id, payload: RefreshCompany, user):
        before = self.store.get("companies", record_id)
        if not before:
            raise NotFound()
        company = CompanyRecord.model_validate(before)
        if company.version != payload.expected_version:
            raise Conflict()
        # At most three known source records; other sources remain visible with their dates.
        selected = sorted(company.projects, key=lambda p: p.source.retrieved_at)[:3]

        def fetch(project):
            try:
                fresh = self.fetch(project.record_id)
                if company.bin not in {party.bin for party in fresh.parties}:
                    return None, "COMPANY_SOURCE_CHANGED"
                return fresh, None
            except AppError as error:
                return None, error.code

        with ThreadPoolExecutor(max_workers=3) as pool:
            outcomes = list(pool.map(fetch, selected))
        fresh = [p for p, error in outcomes if p is not None]
        errors = [error for p, error in outcomes if error]
        fact, directory_error = self.directory_fact(company.bin)
        if directory_error:
            errors.append(directory_error)

        def update(tx):
            current = tx.get("companies", record_id)
            if not current or current["version"] != payload.expected_version:
                raise Conflict()
            updated = self._company(current, company.bin, fresh, [fact] if fact else [])
            updated.last_error = errors[0] if errors else None
            # A failed attempt is not a successful refresh of the stored snapshot.
            if not fresh and fact is None:
                updated.updated_at = company.updated_at
            tx.set("companies", record_id, serialize(updated))
            event = self._event(
                user,
                record_id,
                "company.refresh",
                {
                    "sourceRecordIds": [p.record_id for p in fresh],
                    "errors": errors,
                    "previousVersion": company.version,
                    "version": updated.version,
                },
            )
            tx.create("auditLogs", event["id"], event)
            return public_profile(updated)

        return self.store.atomic(update)
