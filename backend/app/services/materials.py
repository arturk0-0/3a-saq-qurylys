"""Unified, backward-compatible material facade and a single atomic human review."""

import base64
import json

from app.core.errors import AppError, Conflict, NotFound
from app.services.material_analysis import hypotheses
from app.services.material_priority import review_priority
from app.services.material_projection import (
    ad_occurrence,
    all_rows,
    digest,
    legacy_fingerprint,
    monitor_occurrence,
    stage_occurrence,
)
from app.services.risk import calculate_risk
from app.services.workspace import serialize


class MaterialService:
    def __init__(self, workspace):
        self.workspace, self.store = workspace, workspace.store
        self._catalog = {}

    def visible(self, row):
        return row and (
            not self.workspace.demo_only
            or row["workspaceScope"] == "demo"
            or row.get("hasPublicLead")
        )

    def require(self, mid, tx=None):
        row = (tx or self.store).get("materials", mid)
        if not self.visible(row):
            raise NotFound()
        return row

    def sync_legacy(self):
        """Idempotent projection/backfill: saved originals are never overwritten/reseeded."""
        filters = [("demo", "==", True)] if self.workspace.demo_only else []
        originals = [("advertisement", r) for r in all_rows(self.store, "advertisements", filters)]
        originals += [("monitoring", r) for r in all_rows(self.store, "monitorItems")]
        originals.sort(
            key=lambda pair: (
                pair[1].get("capturedAt", pair[1].get("createdAt", "")),
                pair[1]["id"],
            )
        )
        for kind, row in originals:
            link = self.store.get("materialLinks", digest(f"legacy:{kind}:{row['id']}"))
            seen = row.get("lastSeenAt", row.get("capturedAt", row.get("createdAt", "")))
            if link and (
                link.get("derived")
                or (
                    link.get("sourceFingerprint") == legacy_fingerprint(row)
                    and link.get("lastSeenAt", "") >= seen
                )
            ):
                continue

            def project(tx, kind=kind, row=row):
                current = tx.get(
                    "advertisements" if kind == "advertisement" else "monitorItems", row["id"]
                )
                derived = tx.get("materialLinks", digest(f"legacy:{kind}:{row['id']}"))
                if current and not (derived or {}).get("derived"):
                    occurrence = (
                        ad_occurrence(tx, current)
                        if kind == "advertisement"
                        else monitor_occurrence(current)
                    )
                    return stage_occurrence(tx, occurrence)

            self.store.atomic(project)
        from app.services.material_legacy import import_legacy_results

        import_legacy_results(self.workspace)

    @staticmethod
    def state(group, reader):
        jobs = [reader.get("materialJobs", key) for key in group["inputIds"]]
        jobs = [j for j in jobs if j]
        proposals = []
        for job in jobs:
            if job["status"] == "ready":
                for h in hypotheses(job):
                    h["decision"] = group.get("decisions", {}).get(h["id"], "pending")
                    h["occurrenceId"] = group.get("inputSources", {}).get(
                        job["id"], job["occurrenceId"]
                    )
                    proposals.append(h)
        states = [j["status"] for j in jobs]
        status = (
            "queued"
            if "queued" in states
            else "running"
            if "running" in states
            else "failed"
            if "failed" in states
            else "ready"
        )
        error = next((j.get("errorCode") for j in jobs if j.get("errorCode")), None)
        unsupported = bool(group.get("externalMediaKeys"))
        if status == "ready" and unsupported:
            status, error = "unsupported", "EXTERNAL_MEDIA_NOT_ANALYZED"
        analysis = {
            "status": status,
            "errorCode": error,
            "canRetry": status == "failed",
            "updatedAt": max((j.get("completedAt") or j["createdAt"] for j in jobs), default=None),
        }
        return jobs, proposals, analysis

    def summary(self, group):
        jobs, proposals, analysis = self.state(group, self.store)
        complex_ = None
        if group.get("complexId"):
            c = self.workspace.complex(group["complexId"])
            complex_ = {"id": c.id, "name": c.name, "version": c.version}
        return {
            "id": group["id"],
            "version": group["version"],
            "title": group["title"],
            "textPreview": group["text"][:400],
            "reviewState": group["reviewState"],
            "origins": group["origins"],
            "platforms": group["platforms"],
            "occurrenceCount": group["occurrenceCount"],
            "firstSeenAt": group["createdAt"],
            "lastSeenAt": group["lastSeenAt"],
            "complex": complex_,
            "priority": review_priority(
                proposals, [j["status"] for j in jobs], group["reviewState"]
            ),
            "analysis": analysis,
        }

    @staticmethod
    def page(rows, cursor, limit, query):
        fingerprint = digest(json.dumps(query, sort_keys=True))[:16]
        snapshot = digest(json.dumps(rows, sort_keys=True))[:16]
        offset = 0
        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
                if decoded["q"] != fingerprint or decoded["s"] != snapshot:
                    raise Conflict("Material list changed; refresh the first page")
                offset = next(i + 1 for i, r in enumerate(rows) if r["id"] == decoded["id"])
            except (ValueError, KeyError, TypeError, StopIteration, UnicodeError):
                raise AppError(422, "INVALID_CURSOR", "Invalid material cursor") from None
        result = rows[offset : offset + limit]
        next_cursor = None
        if offset + limit < len(rows):
            payload = {"q": fingerprint, "s": snapshot, "id": result[-1]["id"]}
            next_cursor = (
                base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
            )
        return {"items": result, "nextCursor": next_cursor}

    def items(
        self,
        *,
        q="",
        review="all",
        origin="all",
        platform=None,
        complex_id=None,
        sort="priority",
        cursor=None,
        limit=30,
    ):
        self.sync_legacy()
        rows = []
        for group in all_rows(self.store, "materials"):
            if not self.visible(group):
                continue
            if review != "all" and group["reviewState"] != review:
                continue
            if origin != "all" and origin not in group["origins"]:
                continue
            if platform and platform.casefold() not in {p.casefold() for p in group["platforms"]}:
                continue
            if complex_id and (group.get("complexId") or self.candidates(group)[1]) != complex_id:
                continue
            if q and q.casefold() not in f"{group['title']} {group['text']}".casefold():
                originals = all_rows(
                    self.store, "materialOccurrences", [("materialId", "==", group["id"])]
                )
                if not any(
                    q.casefold() in f"{r['text']} {r['account']} {r['originalUrl']}".casefold()
                    for r in originals
                ):
                    continue
            rows.append(self.summary(group))
        rows.sort(key=lambda r: (r["lastSeenAt"], r["id"]), reverse=True)
        if sort == "priority":
            rows.sort(
                key=lambda r: (
                    r["reviewState"] != "needs_review",
                    -(r["priority"]["score"] if r["priority"]["score"] is not None else -1),
                )
            )
        query = dict(
            q=q, review=review, origin=origin, platform=platform, complexId=complex_id, sort=sort
        )
        return self.page(rows, cursor, limit, query)

    def occurrences(self, mid, cursor=None, limit=20):
        group = self.require(mid)
        rows = list(all_rows(self.store, "materialOccurrences", [("materialId", "==", mid)]))
        rows.sort(key=lambda r: (r["capturedAt"], r["id"]), reverse=True)
        output = []
        for row in rows:
            media = []
            for m in row["media"]:
                jid = digest(
                    f"{row['workspaceScope']}:{digest(row['text'])}:image:{m.get('sha256')}"
                )
                job = self.store.get("materialJobs", jid) if m.get("sha256") else None
                media.append(
                    {
                        k: v
                        for k, v in {
                            **m,
                            "analyzed": bool(job and job["status"] == "ready"),
                        }.items()
                        if k != "sha256"
                    }
                )
            output.append(
                {
                    k: row[k]
                    for k in [
                        "id",
                        "origin",
                        "platform",
                        "account",
                        "originalUrl",
                        "publishedAt",
                        "capturedAt",
                        "text",
                        "legacyKind",
                        "legacyId",
                    ]
                }
                | {"media": media}
            )
        return self.page(output, cursor, limit, {"material": mid, "version": group["version"]})

    def detail(self, mid):
        # Legacy IDs are resolved without scanning a client-side first page.
        row = self.store.get("materials", mid)
        if not row:
            self.sync_legacy()
            for kind in ["monitoring", "advertisement"]:
                link = self.store.get("materialLinks", digest(f"legacy:{kind}:{mid}"))
                if link:
                    mid = link["materialId"]
                    break
        group = self.require(mid)
        _, proposals, _ = self.state(group, self.store)
        first = self.occurrences(mid)
        confirmed = (
            calculate_risk(self.workspace.complex(group["complexId"]).factors)
            if group.get("complexId")
            else None
        )
        candidates, _ = self.candidates(group)
        return {
            **self.summary(group),
            "text": group["text"],
            "revisionId": group["revisionId"],
            "occurrences": first["items"],
            "nextOccurrenceCursor": first["nextCursor"],
            "hypotheses": [
                {k: v for k, v in h.items() if not k.startswith("_")} for h in proposals
            ],
            "complexCandidates": candidates,
            "confirmedRisk": serialize(confirmed) if confirmed else None,
            "review": group.get("review"),
        }

    def candidates(self, group):
        scope = group["workspaceScope"]
        if self.workspace.demo_only and scope != "demo":
            return [], None
        from app.services.matching import normalized_name

        if scope not in self._catalog:
            self._catalog[scope] = list(
                all_rows(self.store, "complexes", [("demo", "==", scope == "demo")])
            )
        text = " " + normalized_name(group["text"]) + " "
        matches, strong = [], []
        for c in self._catalog[scope]:
            if any(
                len(normalized_name(name)) >= 5 and (" " + normalized_name(name) + " ") in text
                for name in [c["name"], *c.get("aliases", [])]
            ):
                matches.append({k: c[k] for k in ["id", "name", "address"]})
                if (" " + normalized_name(c["city"]) + " ") in text or normalized_name(
                    c["address"]
                ) in text:
                    strong.append(c["id"])
        return matches, strong[0] if len(strong) == 1 else None

    def priorities_for_complexes(self):
        by_complex = {}
        for group in all_rows(self.store, "materials"):
            if not self.visible(group) or group["reviewState"] != "needs_review":
                continue
            cid = group.get("complexId") or self.candidates(group)[1]
            if cid:
                jobs, proposals, _ = self.state(group, self.store)
                found, states = by_complex.setdefault(cid, ([], []))
                found.extend(proposals)
                states.extend(j["status"] for j in jobs)
        return {
            cid: review_priority(proposals, states)
            for cid, (proposals, states) in by_complex.items()
        }

    def priority_for_complex(self, cid):
        return self.priorities_for_complexes().get(cid, review_priority([], []))

    def retry(self, mid, payload, user):
        request_key = digest("retry:" + str(payload.request_id))
        fingerprint = digest(payload.model_dump_json(by_alias=True) + mid + user.uid)

        def retry(tx):
            group = self.require(mid, tx)
            saved = tx.get("materialReviews", request_key)
            jobs, _, _ = self.state(group, tx)
            if saved:
                if saved["fingerprint"] != fingerprint:
                    raise Conflict("Request ID already used")
                return
            if group["version"] != payload.expected_version:
                raise Conflict()
            failed = [j for j in jobs if j["status"] == "failed"]
            if not failed:
                raise Conflict("Only failed analysis may be retried")
            for j in failed:
                tx.set(
                    "materialJobs",
                    j["id"],
                    {
                        **j,
                        "status": "queued",
                        "errorCode": None,
                        "attemptToken": None,
                        "nextAttemptAt": None,
                        "leaseUntil": None,
                    },
                )
            tx.set("materials", mid, {**group, "version": group["version"] + 1})
            tx.create(
                "materialReviews", request_key, {"id": request_key, "fingerprint": fingerprint}
            )

        self.store.atomic(retry)
        return self.detail(mid)

    def review(self, mid, payload, user):
        from app.services.material_review import review_material

        return review_material(self, mid, payload, user)
