"""Transactional intake projection. No network calls, AI decisions or risk writes."""

import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from app.core.errors import AppError
from app.models.common import utc_now


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def normalized_text(text):
    # Keep digits, punctuation and negation: changed payment terms are a new input.
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def public_url(url):
    parts = urlsplit(str(url))
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def all_rows(store, collection, filters=None):
    """Page the whole matching collection. Never mistake the first page for all results."""
    after = None
    while True:
        rows = store.list(collection, filters=filters or [], after_id=after, limit=200)
        yield from rows
        if len(rows) < 200:
            return
        after = rows[-1]["id"]


def legacy_fingerprint(row):
    keys = [
        "text",
        "attachmentIds",
        "sourceUrl",
        "originalUrl",
        "platform",
        "platforms",
        "account",
        "media",
        "complexId",
        "advertisementId",
    ]
    return digest(json.dumps({key: row.get(key) for key in keys}, sort_keys=True))


def ad_occurrence(tx, ad, evidence_overrides=None):
    row = ad.model_dump(mode="json", by_alias=True) if hasattr(ad, "model_dump") else ad
    media = []
    for eid in row.get("attachmentIds", []):
        evidence = (evidence_overrides or {}).get(eid) or tx.get("evidence", eid)
        if evidence and evidence.get("storagePath") and evidence.get("sha256"):
            media.append(
                {
                    "id": eid,
                    "kind": "image",
                    "url": f"/api/v1/evidence/{eid}/file",
                    "availability": "private",
                    "analyzed": False,
                    "sha256": evidence["sha256"],
                }
            )
    return {
        "sourceFingerprint": legacy_fingerprint(row),
        "legacyKind": "advertisement",
        "legacyId": row["id"],
        "origin": "manual",
        "workspaceScope": "demo" if row.get("demo") else "live",
        "platform": row["platform"],
        "account": row["account"],
        "originalUrl": public_url(row["sourceUrl"]),
        "publishedAt": row.get("publishedAt"),
        "capturedAt": row["capturedAt"],
        "lastSeenAt": row["capturedAt"],
        "text": row["text"],
        "title": row["text"][:100],
        "media": media,
        "complexId": row["complexId"]
        if row.get("linkageStatus", "confirmed") == "confirmed"
        else None,
        "advertisementId": row["id"],
        "hasPublicLead": False,
    }


def monitor_occurrence(item):
    row = item.model_dump(mode="json", by_alias=True) if hasattr(item, "model_dump") else item
    media = [
        {
            "id": digest(f"{row['id']}:{i}"),
            "kind": m["kind"],
            "url": public_url(m["url"]),
            "availability": "external",
            "analyzed": False,
        }
        for i, m in enumerate(row.get("media", []))
    ]
    return {
        "sourceFingerprint": legacy_fingerprint(row),
        "legacyKind": "monitoring",
        "legacyId": row["id"],
        "origin": "automatic",
        "workspaceScope": "live",
        "platform": {"instagram_ad": "Instagram", "telegram_post": "Telegram"}.get(
            row["contentKind"], "Web"
        ),
        "account": row.get("account", ""),
        "originalUrl": public_url(row["originalUrl"]),
        "publishedAt": row.get("publishedAt"),
        "capturedAt": row["createdAt"],
        "lastSeenAt": row["lastSeenAt"],
        "text": row["text"],
        "title": row["title"],
        "media": media,
        "complexId": None,
        "advertisementId": row.get("advertisementId"),
        "hasPublicLead": True,
        "legacyReviewState": "dismissed" if row.get("status") == "dismissed" else "needs_review",
    }


def stage_occurrence(tx, occurrence):
    """Call after other transaction reads and BEFORE other writes (Firestore requirement)."""
    scope, text = occurrence["workspaceScope"], occurrence["text"]
    content = digest(normalized_text(text))
    # Remote media are provenance only: URLs/previews are never claimed to be analyzed.
    media_key = [
        (m["kind"], m.get("sha256") or urlsplit(m.get("url") or "").path)
        for m in occurrence["media"]
    ]
    oid = digest(
        f"{scope}:{occurrence['legacyKind']}:{occurrence['legacyId']}:"
        + digest(text)
        + json.dumps(media_key, sort_keys=True)
    )
    legacy_key = digest(f"legacy:{occurrence['legacyKind']}:{occurrence['legacyId']}")
    alias_key = digest(f"content:{scope}:{content}")
    origin_key = digest(
        f"origin:{scope}:{occurrence['legacyKind']}:"
        f"{occurrence.get('complexId') or ''}:{occurrence['originalUrl']}"
    )
    links = {key: tx.get("materialLinks", key) for key in [legacy_key, alias_key, origin_key]}
    link = links[legacy_key] or links[origin_key] or links[alias_key]
    mid = link["materialId"] if link else digest(f"material:{scope}:{content}")
    group = tx.get("materials", mid)
    # A generic identical caption is insufficient to merge two explicitly different ЖК.
    if (
        group
        and group.get("complexId")
        and occurrence.get("complexId")
        and group["complexId"] != occurrence["complexId"]
    ):
        mid = digest(f"material:{scope}:{content}:{occurrence['complexId']}")
        group = tx.get("materials", mid)
    publication_key = digest(f"publication:{mid}:{occurrence['originalUrl'] or legacy_key}")
    publication = tx.get("materialLinks", publication_key)
    links[publication_key] = publication
    old = tx.get("materialOccurrences", oid)
    if old:
        if links[legacy_key] and links[legacy_key].get("sourceFingerprint") != occurrence.get(
            "sourceFingerprint"
        ):
            tx.set(
                "materialLinks",
                legacy_key,
                {
                    **links[legacy_key],
                    "sourceFingerprint": occurrence.get("sourceFingerprint"),
                    "lastSeenAt": occurrence["lastSeenAt"],
                },
            )
        if old["lastSeenAt"] < occurrence["lastSeenAt"]:
            tx.set("materialOccurrences", oid, {**old, "lastSeenAt": occurrence["lastSeenAt"]})
            if group and group["lastSeenAt"] < occurrence["lastSeenAt"]:
                tx.set("materials", mid, {**group, "lastSeenAt": occurrence["lastSeenAt"]})
        return mid
    now = utc_now().isoformat()
    occurrence = {**occurrence, "id": oid, "materialId": mid, "contentKey": content}
    same_content = bool(group and group["contentKey"] == content)
    inputs = list(group.get("inputIds", [])) if same_content else []
    additions = [(digest(f"{scope}:{digest(text)}:text"), None)]
    additions += [
        (digest(f"{scope}:{digest(text)}:image:{m['sha256']}"), m["id"])
        for m in occurrence["media"]
        if m.get("sha256")
    ]
    sources = dict(group.get("inputSources", {})) if same_content else {}
    if same_content and inputs:
        # Equivalent formatting is a new occurrence, not another paid text request.
        additions = [a for a in additions if a[1] is not None]
    jobs = {jid: tx.get("materialJobs", jid) for jid, _ in additions}
    for jid, _ in additions:
        if jid not in inputs:
            inputs.append(jid)
        sources.setdefault(jid, oid)
    if len(inputs) > 60:
        raise AppError(
            422,
            "MATERIAL_MEDIA_LIMIT",
            "Split a material with more than 60 distinct analysis inputs",
        )
    external_keys = list(group.get("externalMediaKeys", [])) if same_content else []
    for m in occurrence["media"]:
        if m["availability"] != "private":
            key = digest(m["kind"] + urlsplit(m.get("url") or "").path)
            if key not in external_keys:
                external_keys.append(key)
    revision = digest(content + ":".join(sorted(inputs)) + ":".join(sorted(external_keys)))
    changed = not group or group["revisionId"] != revision
    initial = {
        "id": mid,
        "workspaceScope": scope,
        "createdAt": occurrence["capturedAt"],
        "version": 0,
        "occurrenceCount": 0,
        "origins": [],
        "platforms": [],
        "complexId": occurrence.get("complexId"),
        "reviewState": occurrence.get("legacyReviewState", "needs_review"),
        "review": None,
        "decisions": {},
    }
    updated = {
        **(group or initial),
        "text": text if changed else group["text"],
        "title": occurrence["title"] or text[:100],
        "contentKey": content,
        "revisionId": revision,
        "inputIds": inputs,
        "inputSources": sources,
        "externalMediaKeys": external_keys,
        "lastSeenAt": max(
            (group or initial).get("lastSeenAt", occurrence["lastSeenAt"]), occurrence["lastSeenAt"]
        ),
        "version": (group or initial)["version"] + 1,
        "occurrenceCount": (group or initial)["occurrenceCount"] + int(publication is None),
        "origins": sorted(set((group or initial)["origins"] + [occurrence["origin"]])),
        "platforms": sorted(set((group or initial)["platforms"] + [occurrence["platform"]])),
        "hasPublicLead": occurrence["hasPublicLead"] or bool((group or {}).get("hasPublicLead")),
    }
    if changed and group:
        updated["reviewState"] = "needs_review"
    if not updated.get("complexId") and occurrence.get("complexId"):
        updated["complexId"] = occurrence["complexId"]
    for jid, image_id in additions:
        if not jobs[jid]:
            tx.create(
                "materialJobs",
                jid,
                {
                    "id": jid,
                    "materialId": mid,
                    "workspaceScope": scope,
                    "occurrenceId": oid,
                    "text": text,
                    "screenshotId": image_id,
                    "screenshotSha": next(
                        (m.get("sha256") for m in occurrence["media"] if m["id"] == image_id), None
                    ),
                    "advertisementId": occurrence.get("advertisementId"),
                    "hasPublicLead": occurrence["hasPublicLead"],
                    "createdAt": now,
                    "status": "queued",
                    "errorCode": None,
                    "completedAt": None,
                    "leaseUntil": None,
                    "attemptToken": None,
                    "extraction": None,
                },
            )
    for key, existing in links.items():
        if existing is None:
            tx.create(
                "materialLinks",
                key,
                {
                    "id": key,
                    "materialId": mid,
                    "sourceFingerprint": occurrence.get("sourceFingerprint")
                    if key == legacy_key
                    else None,
                    "lastSeenAt": occurrence["lastSeenAt"],
                },
            )
        elif key == legacy_key and existing["materialId"] == mid:
            tx.set(
                "materialLinks",
                key,
                {
                    **existing,
                    "sourceFingerprint": occurrence.get("sourceFingerprint"),
                    "lastSeenAt": occurrence["lastSeenAt"],
                },
            )
    tx.create("materialOccurrences", oid, occurrence)
    tx.set("materials", mid, updated)
    return mid
