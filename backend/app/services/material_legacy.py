"""Reuse exact saved text/image results and human findings, without new provider calls."""

import hashlib
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.core.errors import AppError
from app.services.gemini import PROMPT_VERSION
from app.services.material_analysis import hypotheses
from app.services.material_projection import all_rows, digest
from app.services.material_provider import input_call_key
from app.services.material_reads import MaterialReads


def import_legacy_results(workspace, files=None):
    store = workspace.store
    filters = [("demo", "==", True)] if workspace.demo_only else []
    runs, rejected, evidence = {}, {}, {}
    for run in all_rows(store, "analysisRuns", filters):
        runs.setdefault(run["advertisementId"], []).append(run)
    for values in runs.values():
        values.sort(key=lambda r: r["createdAt"], reverse=True)
    for h in all_rows(store, "aiHypotheses", filters):
        if h["status"] == "rejected":
            rejected.setdefault(h["advertisementId"], set()).add((h["code"], h["quote"]))
    for e in all_rows(store, "evidence", filters):
        if e["status"] == "confirmed" and e.get("advertisementId"):
            evidence.setdefault(e["advertisementId"], []).append(e)
    downloads = {}
    groups = [
        g
        for g in all_rows(store, "materials")
        if not workspace.demo_only or g["workspaceScope"] in {"demo", "public"}
    ]
    reader = MaterialReads(store)
    reader.load("materialJobs", (jid for g in groups for jid in g["inputIds"]))
    jobs = [reader.get("materialJobs", jid) for g in groups for jid in g["inputIds"]]
    jobs = [j for j in jobs if j]
    reader.load("materialOccurrences", (j["occurrenceId"] for j in jobs))
    sources = [reader.get("materialOccurrences", j["occurrenceId"]) for j in jobs]
    reader.load(
        "monitorItems",
        (s["legacyId"] for s in sources if s and s["legacyKind"] == "monitoring"),
    )
    reader.load("complexes", (g.get("complexId") for g in groups))
    for group in groups:
        if workspace.demo_only and group["workspaceScope"] not in {"demo", "public"}:
            continue
        for jid in group["inputIds"]:
            job = reader.get("materialJobs", jid)
            if not job:
                continue
            source = reader.get("materialOccurrences", job["occurrenceId"])
            if not source:
                continue
            old = None
            reusable = job["status"] in {"queued", "failed"} and not job.get("attemptToken")
            if reusable and source["legacyKind"] == "monitoring" and not job.get("screenshotId"):
                candidate = reader.get("monitorItems", source["legacyId"])
                if (
                    candidate
                    and candidate["text"] == job["text"]
                    and candidate.get("aiStatus") in {"succeeded", "failed", "running"}
                ):
                    old = {
                        "id": candidate.get("aiRequestId"),
                        "status": candidate["aiStatus"],
                        "extraction": candidate.get("extraction"),
                        "model": candidate.get("aiModel"),
                        "promptVersion": candidate.get("aiPromptVersion"),
                        "errorCode": candidate.get("aiError"),
                        "completedAt": candidate.get("aiCompletedAt"),
                        "createdAt": candidate.get("aiStartedAt") or candidate["lastSeenAt"],
                    }
            elif reusable:
                for candidate in runs.get(source.get("advertisementId"), []):
                    sid = candidate.get("screenshotId")
                    if bool(sid) != bool(job.get("screenshotId")):
                        continue
                    image = None
                    if sid:
                        record = store.get("evidence", sid)
                        if (
                            not files
                            or not record
                            or record.get("sha256") != job.get("screenshotSha")
                        ):
                            continue
                        try:
                            if sid not in downloads:
                                downloads[sid] = files.download(sid)[0]
                            image = downloads[sid]
                        except AppError:
                            continue
                    expected = hashlib.sha256(job["text"].encode() + (image or b"")).hexdigest()
                    if (
                        candidate["status"] == "succeeded"
                        and candidate.get("inputSha256") == expected
                    ):
                        old = candidate
                        break
                    if candidate["status"] in {"failed", "running"}:
                        # Legacy ad text is immutable; uncertain calls need explicit retry.
                        old = candidate
                        break
            if old and old.get("errorCode") == "AI_DAILY_LIMIT":
                old = None
            legacy_key = digest(str(old)) if old else None
            if (
                old
                and job["status"] in {"queued", "failed"}
                and not job.get("attemptToken")
                and job.get("legacyRunKey") != legacy_key
            ):

                def reuse(tx, jid=jid, job=job, old=old, group=group, legacy_key=legacy_key):
                    current = tx.get("materialJobs", jid)
                    current_group = tx.get("materials", group["id"])
                    settings = SimpleNamespace(gemini_model=old.get("model") or "")
                    key = input_call_key(
                        job["workspaceScope"], job["text"], job.get("screenshotSha") or "", settings
                    )
                    cached = tx.get("materialProviderCalls", key)
                    if (
                        not current
                        or current["status"] not in {"queued", "failed"}
                        or current.get("attemptToken")
                    ):
                        return
                    good = old["status"] == "succeeded" and old.get("extraction")
                    tx.set(
                        "materials",
                        group["id"],
                        {**current_group, "version": current_group["version"] + 1},
                    )
                    tx.set(
                        "materialJobs",
                        jid,
                        {
                            **current,
                            "status": "ready" if good else "failed",
                            "extraction": old.get("extraction") if good else None,
                            "legacyRunKey": legacy_key,
                            "errorCode": None
                            if good
                            else (old.get("errorCode") or "AI_OUTCOME_UNKNOWN"),
                            "model": old.get("model"),
                            "promptVersion": old.get("promptVersion"),
                            "completedAt": old.get("completedAt") or group["createdAt"],
                        },
                    )
                    if (
                        (cached is None or cached.get("attemptToken") == "legacy")
                        and old.get("model")
                        and old.get("promptVersion") == PROMPT_VERSION
                    ):
                        tx.set(
                            "materialProviderCalls",
                            key,
                            {
                                "id": key,
                                "status": "ready"
                                if good
                                else "running"
                                if old["status"] == "running"
                                else "failed",
                                "leaseUntil": (
                                    datetime.fromisoformat(
                                        old.get("createdAt") or group["createdAt"]
                                    )
                                    + timedelta(minutes=10)
                                ).isoformat(),
                                "attemptToken": "legacy",
                                "model": old["model"],
                                "promptVersion": PROMPT_VERSION,
                                "extraction": old.get("extraction") if good else None,
                                "errorCode": None if good else "AI_OUTCOME_UNKNOWN",
                                "createdAt": group["createdAt"],
                            },
                        )

                store.atomic(reuse)
                job = store.get("materialJobs", jid)
            if job["status"] != "ready":
                continue
            decisions, legacy_evidence = {}, {}
            cid = group.get("complexId")
            complex_ = reader.get("complexes", cid) if cid else None
            ad_id = source.get("advertisementId")
            for h in hypotheses(job):
                if (h["code"], h["quote"]) in rejected.get(ad_id, set()):
                    decisions[h["id"]] = "rejected"
                for e in evidence.get(ad_id, []):
                    flag = (
                        "paymentOfferVerified" if h["code"] == "R2" else "activeAdvertisingVerified"
                    )
                    if (
                        e.get(flag)
                        and h["quote"] in e["excerpt"]
                        and complex_
                        and any(
                            f["code"] == h["code"]
                            and f["status"] == "confirmed"
                            and e["id"] in f["evidenceIds"]
                            for f in complex_["factors"]
                        )
                    ):
                        decisions[h["id"]] = "confirmed"
                        legacy_evidence.setdefault(h["id"], []).append(e["id"])
            # Do not open a write transaction for an unchanged historical decision.
            # The callback still rechecks the current revision and missing keys.
            missing_decisions = set(decisions) - set(group.get("decisions", {}))
            changed_refs = {**group.get("legacyEvidence", {}), **legacy_evidence} != group.get(
                "legacyEvidence", {}
            )
            if decisions and (missing_decisions or changed_refs):

                def preserve(tx, group=group, decisions=decisions, legacy_evidence=legacy_evidence):
                    current = tx.get("materials", group["id"])
                    if current and current["revisionId"] == group["revisionId"]:
                        missing = {
                            k: v
                            for k, v in decisions.items()
                            if k not in current.get("decisions", {})
                        }
                        refs = {**current.get("legacyEvidence", {}), **legacy_evidence}
                        if missing or refs != current.get("legacyEvidence", {}):
                            tx.set(
                                "materials",
                                group["id"],
                                {
                                    **current,
                                    "decisions": {**current.get("decisions", {}), **missing},
                                    "legacyEvidence": refs,
                                    "version": current["version"] + 1,
                                },
                            )

                store.atomic(preserve)
