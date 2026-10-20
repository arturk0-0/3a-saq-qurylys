"""Reuse saved analyses and human findings, never AI acceptance as confirmation."""

from app.services.material_analysis import hypotheses
from app.services.material_projection import all_rows, digest


def import_legacy_results(workspace):
    store = workspace.store
    filters = [("demo", "==", True)] if workspace.demo_only else []
    runs = {}
    for r in all_rows(store, "analysisRuns", filters):
        if r["status"] == "succeeded" and not r.get("screenshotId"):
            old = runs.get(r["advertisementId"])
            if not old or r["createdAt"] > old["createdAt"]:
                runs[r["advertisementId"]] = r
    rejected = {}
    for h in all_rows(store, "aiHypotheses", filters):
        if h["status"] == "rejected":
            rejected.setdefault(h["advertisementId"], set()).add((h["code"], h["quote"]))
    evidence = {}
    for e in all_rows(store, "evidence", filters):
        if e["status"] == "confirmed" and e.get("advertisementId"):
            evidence.setdefault(e["advertisementId"], []).append(e)
    for group in all_rows(store, "materials"):
        if (
            workspace.demo_only
            and group["workspaceScope"] != "demo"
            and not group.get("hasPublicLead")
        ):
            continue
        for jid in group["inputIds"]:
            job = store.get("materialJobs", jid)
            if not job or job.get("screenshotId"):
                continue
            source = store.get("materialOccurrences", job["occurrenceId"])
            if not source:
                continue
            result = None
            if source["legacyKind"] == "monitoring":
                old = store.get("monitorItems", source["legacyId"])
                if old and old.get("aiStatus") == "succeeded" and old["text"] == job["text"]:
                    result = old.get("extraction")
            else:
                old = runs.get(source["legacyId"])
                if old and old.get("inputSha256") == digest(job["text"]):
                    result = old.get("extraction")
            if result and job["status"] == "queued":

                def reuse(tx, jid=jid, result=result, old=old, group=group):
                    current = tx.get("materialJobs", jid)
                    if (
                        current
                        and current["status"] == "queued"
                        and not current.get("attemptToken")
                    ):
                        tx.set(
                            "materialJobs",
                            jid,
                            {
                                **current,
                                "status": "ready",
                                "extraction": result,
                                "errorCode": None,
                                "completedAt": (old or {}).get("completedAt") or group["createdAt"],
                            },
                        )

                store.atomic(reuse)
                job = store.get("materialJobs", jid)
            if job["status"] != "ready":
                continue
            decisions = {}
            cid = group.get("complexId")
            complex_ = store.get("complexes", cid) if cid else None
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
            if decisions:

                def preserve(tx, group=group, decisions=decisions):
                    current = tx.get("materials", group["id"])
                    if current and current["revisionId"] == group["revisionId"]:
                        missing = {
                            k: v
                            for k, v in decisions.items()
                            if k not in current.get("decisions", {})
                        }
                        if missing:
                            tx.set(
                                "materials",
                                group["id"],
                                {
                                    **current,
                                    "decisions": {**current.get("decisions", {}), **missing},
                                    "version": current["version"] + 1,
                                },
                            )

                store.atomic(preserve)
