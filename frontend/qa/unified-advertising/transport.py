"""Synthetic contract transport for UI QA ONLY. Not a backend implementation.

Review returns a fixed golden fixture, not a risk calculation or database write.
The application never imports this file. Existing non-material APIs stay local.
"""

import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FIXTURES = json.loads((Path(__file__).parent / "fixtures.json").read_text())


class MaterialsTransport:
    def __init__(self, ad_id, image_id):
        self.details = {}
        for name in ["material", "queued", "failed", "video"]:
            item = copy.deepcopy(FIXTURES[name])
            item["occurrences"][0]["legacyId"] = ad_id
            self.details[item["id"]] = item
        self.details["m1"]["occurrences"][0]["media"] = [
            {
                "id": image_id,
                "kind": "image",
                "url": None,
                "availability": "private",
                "analyzed": True,
            }
        ]
        checked = copy.deepcopy(FIXTURES["saved"])
        checked.update(
            id="reviewed-example",
            title="DEMO — ранее проверенный материал",
            textPreview="Другая учебная публикация",
            text="Другая учебная публикация",
        )
        self.details[checked["id"]] = checked
        self.requests = []
        self.reviews = []
        self.retries = []
        self.mode = None
        self.list_error = False
        self.empty = False
        self.occurrence_error = False
        self.cache = {}

    def handle(self, route):
        request = route.request
        path = urlsplit(request.url).path
        query = parse_qs(urlsplit(request.url).query)
        self.requests.append((request.method, path, query))
        if request.headers.get("authorization") != "Bearer qa-local-analyst":
            route.fulfill(status=401, json={"code": "INVALID_TOKEN"})
            return
        if path == "/api/v1/materials":
            if self.list_error:
                route.fulfill(
                    status=503,
                    json={
                        "code": "QA_UNAVAILABLE",
                        "message": "PRIVATE PROVIDER DETAILS",
                    },
                )
                return
            items = [] if self.empty else list(self.details.values())
            for key, field in [
                ("review", "reviewState"),
                ("origin", "origins"),
                ("platform", "platforms"),
            ]:
                value = query.get(key, ["all"])[0]
                if value != "all":
                    items = [
                        item
                        for item in items
                        if (
                            value in item[field]
                            if isinstance(item[field], list)
                            else value == item[field]
                        )
                    ]
            if query.get("q"):
                term = query["q"][0].lower()
                items = [
                    item
                    for item in items
                    if term in (item["title"] + item["textPreview"]).lower()
                ]
            if query.get("complexId"):
                items = [
                    item
                    for item in items
                    if item["complex"]
                    and item["complex"]["id"] == query["complexId"][0]
                ]
            # Short pages deliberately exercise the opaque cursor UI.
            start = int(query.get("cursor", ["0"])[0])
            page = items[start : start + 2]
            route.fulfill(
                json={
                    "items": page,
                    "nextCursor": str(start + 2) if len(items) > start + 2 else None,
                }
            )
            return
        parts = path.split("/")
        item = self.details.get(parts[4]) if len(parts) > 4 else None
        if item is None:
            route.fulfill(status=404, json={"code": "NOT_FOUND"})
            return
        if path.endswith("/occurrences"):
            if self.occurrence_error:
                self.occurrence_error = False
                route.fulfill(status=503, json={"code": "QA_UNAVAILABLE"})
            else:
                route.fulfill(
                    json={"items": [FIXTURES["lastOccurrence"]], "nextCursor": None}
                )
            return
        if "/occurrences/" in path:
            route.fulfill(json=FIXTURES["lastOccurrence"])
            return
        if path.endswith("/history"):
            route.fulfill(json={"items": [], "nextCursor": None})
            return
        if request.method == "GET":
            route.fulfill(json=item)
            return
        body = request.post_data_json
        if path.endswith("/review"):
            self.reviews.append(copy.deepcopy(body))
            cached = self.cache.get(body["requestId"])
            if cached:
                route.fulfill(json=cached)
                return
            if self.mode == "conflict":
                self.mode = None
                item["version"] += 1
                item["revisionId"] = "revision-refreshed"
                route.fulfill(status=409, json={"code": "CONFLICT"})
                return
            if self.mode == "invalid":
                self.mode = None
                route.fulfill(
                    status=422,
                    json={
                        "code": "VALIDATION_ERROR",
                        "message": "PRIVATE PROVIDER DETAILS",
                    },
                )
                return
            assert body["expectedVersion"] == item["version"]
            assert body["revisionId"] == item["revisionId"]
            # Fixed golden response; this deliberately does not emulate R1-R6.
            saved = copy.deepcopy(FIXTURES["saved"])
            saved.update(
                id=item["id"],
                version=item["version"] + 1,
                revisionId=item["revisionId"],
                occurrences=item["occurrences"],
                reviewState=body["disposition"],
            )
            saved["review"]["notes"] = body["notes"]
            self.details[item["id"]] = saved
            self.cache[body["requestId"]] = saved
            if self.mode == "lost_response":
                self.mode = None
                route.abort()
            else:
                route.fulfill(json=saved)
            return
        if path.endswith("/retry-analysis"):
            self.retries.append(copy.deepcopy(body))
            assert (
                item["analysis"]["status"] == "failed" and item["analysis"]["canRetry"]
            )
            if self.mode == "quota":
                self.mode = None
                route.fulfill(status=429, json={"code": "AI_DAILY_LIMIT"})
                return
            item["version"] += 1
            item["analysis"].update(status="queued", canRetry=False, errorCode=None)
            route.fulfill(json=item)
            return
        route.fulfill(status=405, json={"code": "METHOD_NOT_ALLOWED"})
