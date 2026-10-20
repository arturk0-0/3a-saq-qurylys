"""One all-or-nothing human decision; no external effects inside a transaction."""

from uuid import uuid4

from app.core.errors import AppError, Conflict
from app.models.common import utc_now
from app.models.entities import Advertisement, Complex, Evidence
from app.models.risk import RiskFactor
from app.services.evidence import validate_factor_evidence
from app.services.material_projection import digest
from app.services.workspace import serialize


def review_material(self, mid, payload, user):
    request_key = digest("review:" + str(payload.request_id))
    fingerprint = digest(payload.model_dump_json(by_alias=True) + mid + user.uid)
    now = utc_now()

    def save(tx):
        group = self.require(mid, tx)
        saved = tx.get("materialReviews", request_key)
        jobs, proposals, analysis = self.state(group, tx)
        if saved:
            if saved["fingerprint"] != fingerprint:
                raise Conflict("Request ID already used")
            return
        if (
            group["version"] != payload.expected_version
            or group["revisionId"] != payload.revision_id
        ):
            raise Conflict()
        known = {h["id"]: h for h in proposals}
        selected = {d.hypothesis_id: d.decision for d in payload.decisions}
        if not set(selected) <= set(known):
            raise AppError(422, "HYPOTHESIS_MISMATCH", "Choose hypotheses from this revision")
        pending = {h["id"] for h in proposals if h["decision"] in {"pending", "insufficient"}}
        if payload.disposition == "reviewed" and (
            analysis["status"] in {"queued", "running"}
            or not pending <= selected.keys()
            or "insufficient" in selected.values()
        ):
            raise AppError(
                422,
                "REVIEW_INCOMPLETE",
                "Decide all pending hypotheses or keep material for review",
            )
        if payload.disposition == "dismissed" and "confirmed" in selected.values():
            raise AppError(
                422, "REVIEW_CONTRADICTION", "Do not dismiss explicitly confirmed findings"
            )
        cid = payload.complex_id or group.get("complexId")
        if group.get("complexId") and cid != group["complexId"]:
            raise Conflict("Existing confirmed evidence cannot be moved to another complex")
        complex_ = self.workspace.complex(cid, tx) if cid else None
        if complex_ and (complex_.demo != (group["workspaceScope"] == "demo")):
            raise AppError(
                422,
                "SCOPE_MISMATCH",
                "Real publications cannot be assigned to fictional complexes",
            )
        if complex_ and complex_.version != payload.expected_complex_version:
            raise Conflict("Refresh the complex before reviewing")
        if "confirmed" in selected.values() and not complex_:
            raise AppError(422, "COMPLEX_REQUIRED", "Choose the actual complex before confirmation")
        occurrences = {
            h["occurrenceId"]: tx.get("materialOccurrences", h["occurrenceId"])
            for h in proposals
            if h["id"] in selected
        }
        current_evidence = {}
        if complex_:
            for f in complex_.factors:
                if f.code in {"R2", "R3"}:
                    for eid in f.evidence_ids:
                        current_evidence[eid] = Evidence.model_validate(
                            self.workspace.require_record("evidence", eid, tx)
                        )
        evidence_changes, advertisements, derived_links = {}, {}, {}
        job_by_id = {j["id"]: j for j in jobs}
        for hid, decision in selected.items():
            if not complex_:
                continue
            h = known[hid]
            occurrence = occurrences[h["occurrenceId"]]
            if not occurrence or occurrence["materialId"] != mid:
                raise Conflict("Original source is unavailable")
            jid = h["_jobId"]
            job = job_by_id[jid]
            ad_id = occurrence.get("advertisementId") or digest(
                f"material-ad:{mid}:{cid}:{occurrence['id']}"
            )
            ad_raw = tx.get("advertisements", ad_id)
            if ad_raw:
                ad = Advertisement.model_validate(ad_raw)
                if ad.complex_id != cid or ad.demo != complex_.demo:
                    raise AppError(422, "EVIDENCE_MISMATCH", "Original belongs to another complex")
            else:
                if not occurrence["originalUrl"]:
                    raise AppError(
                        422, "SOURCE_REQUIRED", "Original URL is required for confirmation"
                    )
                ad = Advertisement(
                    id=ad_id,
                    complex_id=cid,
                    platform=occurrence["platform"],
                    account=occurrence["account"] or "Не указан",
                    source_url=occurrence["originalUrl"],
                    text=occurrence["text"],
                    published_at=occurrence["publishedAt"],
                    captured_at=occurrence["capturedAt"],
                    created_by=user.uid,
                    demo=complex_.demo,
                )
                advertisements[ad.id] = ad
                link_key = digest(f"legacy:advertisement:{ad.id}")
                old_link = tx.get("materialLinks", link_key)
                if old_link and old_link["materialId"] != mid:
                    raise Conflict("Derived advertisement link changed")
                if not old_link:
                    derived_links[link_key] = {
                        "id": link_key,
                        "materialId": mid,
                        "derived": True,
                    }
            screenshot = None
            if job.get("screenshotId"):
                screenshot = Evidence.model_validate(
                    self.workspace.require_record(
                        "evidence",
                        next(
                            (
                                m["id"]
                                for m in occurrence["media"]
                                if m.get("sha256") == job.get("screenshotSha")
                            ),
                            job["screenshotId"],
                        ),
                        tx,
                    )
                )
                if screenshot.advertisement_id != ad.id or screenshot.complex_id != cid:
                    raise AppError(
                        422, "EVIDENCE_MISMATCH", "Screenshot belongs to another original"
                    )
            elif h["quote"] not in occurrence["text"]:
                raise AppError(422, "EXCERPT_MISMATCH", "Quote does not occur in original source")
            eid = digest(f"material-evidence:{hid}:{cid}")
            old = tx.get("evidence", eid)
            item = Evidence(
                id=eid,
                complex_id=cid,
                advertisement_id=ad.id,
                type="screenshot" if screenshot else "advertisement",
                source_url=ad.source_url,
                source_reference=f"Material {mid}; revision {group['revisionId']}; {jid}",
                excerpt=h["quote"],
                captured_at=occurrence["capturedAt"],
                status="confirmed"
                if decision == "confirmed"
                else "rejected"
                if decision == "rejected"
                else "unknown",
                reviewer=user.uid,
                reviewed_at=now,
                demo=complex_.demo,
                version=(old or {}).get("version", 0) + 1,
                storage_path=screenshot.storage_path if screenshot else None,
                sha256=screenshot.sha256 if screenshot else None,
                media_type=screenshot.media_type if screenshot else None,
                size_bytes=screenshot.size_bytes if screenshot else None,
                payment_offer_verified=decision == "confirmed" and h["code"] == "R2",
                active_advertising_verified=decision == "confirmed" and h["code"] == "R3",
                construction_verified=decision == "confirmed" and h["code"] == "R3",
            )
            evidence_changes[eid] = item
        new_complex = None
        if complex_ and evidence_changes:
            factors = {f.code: f for f in complex_.factors}
            touched = {known[hid]["code"] for hid in selected}
            for code in touched:
                previous = factors.get(code, RiskFactor(code=code))
                superseded = {
                    eid
                    for hid in selected
                    if known[hid]["code"] == code
                    for eid in group.get("legacyEvidence", {}).get(hid, [])
                }
                ids = (
                    [
                        eid
                        for eid in previous.evidence_ids
                        if eid not in evidence_changes and eid not in superseded
                    ]
                    if previous.status == "confirmed"
                    else []
                )
                ids += [
                    e.id
                    for e in evidence_changes.values()
                    if e.status == "confirmed"
                    and any(
                        known[hid]["code"] == code
                        and e.id == digest(f"material-evidence:{hid}:{cid}")
                        for hid in selected
                    )
                ]
                refs = [evidence_changes.get(eid) or current_evidence[eid] for eid in ids]
                if len(ids) > 30:
                    raise AppError(422, "FACTOR_EVIDENCE_LIMIT", "Factor evidence limit reached")
                if ids:
                    try:
                        validate_factor_evidence(code, complex_, refs)
                    except ValueError as error:
                        raise AppError(422, "FACTOR_NOT_SUPPORTED", str(error)) from None
                if (
                    not ids
                    and previous.status != "confirmed"
                    and not any(
                        selected[hid] == "confirmed" and known[hid]["code"] == code
                        for hid in selected
                    )
                ):
                    continue
                factors[code] = RiskFactor(
                    code=code,
                    status="confirmed" if ids else "unknown",
                    evidence_ids=ids,
                    reviewer=user.uid,
                    reviewed_at=now,
                    notes=payload.notes,
                )
            new_complex = Complex.model_validate(
                {
                    **complex_.model_dump(),
                    "factors": list(factors.values()),
                    "version": complex_.version + 1,
                    "updated_at": now,
                }
            )
        updated = {
            **group,
            "complexId": cid,
            "version": group["version"] + 1,
            "reviewState": payload.disposition,
            "decisions": {**group.get("decisions", {}), **selected},
            "review": {
                "notes": payload.notes,
                "reviewedAt": now.isoformat(),
                "reviewerDisplayName": user.display_name,
            },
        }
        event = {
            "id": uuid4().hex,
            "entityType": "material",
            "entityId": mid,
            "complexId": cid,
            "demo": group["workspaceScope"] == "demo",
            "actorUid": user.uid,
            "reviewerDisplayName": user.display_name,
            "createdAt": now.isoformat(),
            "action": "material.review",
            "details": {
                "revisionId": group["revisionId"],
                "decisions": selected,
                "notes": payload.notes,
                "disposition": payload.disposition,
            },
        }
        # Every read above precedes every write: one Firestore commit or no changes.
        for key, link in derived_links.items():
            tx.create("materialLinks", key, link)
        for ad in advertisements.values():
            tx.create("advertisements", ad.id, serialize(ad))
        for e in evidence_changes.values():
            tx.set("evidence", e.id, serialize(e))
        if new_complex:
            tx.set("complexes", cid, serialize(new_complex))
        tx.set("materials", mid, updated)
        tx.create("materialReviews", request_key, {"id": request_key, "fingerprint": fingerprint})
        tx.create("auditLogs", event["id"], event)

    self.store.atomic(save)
    return self.detail(mid)
