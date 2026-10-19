"""Bounded reads of public registries. Matches are candidates, never legal findings."""

import csv
import hashlib
import io
import json
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.core.errors import AppError
from app.models.common import utc_now
from app.models.monitoring import RegistryDocument

HOME_API = "https://api.homeportal.kz/api/v1/"
ASHYQ_PAGE = "https://ashyq.data.gov.kz/dataset/magda-ds-b80110e9-218a-42ba-b8c8-01fa5e4c82c8"
ASHYQ_CSV = "https://s3.sdu.gov.kz/" + quote(
    "magda-datasets/miir_kazreestr_du_objects/"
    "Объекты с долевым участием в жилищном строительстве.csv",
    safe="/",
)
MAX_BYTES = 2_000_000
MAX_RESULTS = 20
_cache_lock = threading.Lock()
_csv_cache = None


def text(value: Any, limit: int = 500) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def vko(value: str) -> bool:
    value = normalized(value)
    if any(x in value for x in ("семей", "семипалатин", "область абай", "абайская")):
        return False
    return any(
        x in value
        for x in (
            "восточно казахстан",
            "шығыс қазақстан",
            "east kazakhstan",
            "усть каменогорск",
            "өскемен",
            "риддер",
            "шемонаих",
            "зайсан",
            "серебрянск",
        )
    )


class RegistryClient:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.transport = transport

    def read(self, method: str, url: str, payload: dict | None = None) -> bytes:
        # Every caller supplies one of the fixed URLs below, never a user URL.
        try:
            deadline = time.monotonic() + 15
            with (
                httpx.Client(
                    timeout=httpx.Timeout(10, connect=3),
                    follow_redirects=False,
                    transport=self.transport,
                    headers={"User-Agent": "SAQ-QURYLYS/1.0 RegistryCheck"},
                ) as client,
                client.stream(method, url, json=payload) as response,
            ):
                if response.status_code != 200:
                    raise AppError(503, "REGISTRY_UNAVAILABLE", "Registry unavailable")
                body = bytearray()
                for chunk in response.iter_bytes(65536):
                    if time.monotonic() > deadline or len(body) + len(chunk) > MAX_BYTES:
                        raise AppError(
                            503, "REGISTRY_RESPONSE_INVALID", "Registry response limited"
                        )
                    body.extend(chunk)
                return bytes(body)
        except httpx.HTTPError:
            raise AppError(503, "REGISTRY_UNAVAILABLE", "Registry unavailable") from None

    def home_search(self, query: str) -> tuple[list[dict], bool]:
        body = self.read(
            "POST",
            HOME_API + "getobjects",
            {
                "authority": "",
                "city_id": None,
                "region_id": 16,
                "search": query,
                "is_paginate": True,
                "build_status": "2",
                "status": "2,3",
            },
        )
        try:
            page = json.loads(body)["data"]["objects"]
            rows = page["data"]
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError()
            candidates = []
            for row in rows[:MAX_RESULTS]:
                if not isinstance(row, dict):
                    raise ValueError()
                region = row.get("region") or {}
                region_name = region.get("ru", "") if isinstance(region, dict) else ""
                if not vko(region_name + " " + text(row.get("address"))):
                    continue
                record_id = str(row.get("id", ""))
                if not re.fullmatch(r"[0-9]{1,15}", record_id):
                    continue
                candidates.append(
                    {
                        "provider": "homeportal",
                        "recordId": record_id,
                        "name": text(row.get("name")),
                        "address": text(row.get("address")),
                        "developer": text(row.get("developerName")),
                        "developerBin": text(row.get("bin"), 12),
                        "holder": text(row.get("authorizedName")),
                        "holderBin": text(row.get("authorizedBin"), 12),
                        "basisLabel": text(row.get("authority")),
                        "reference": "",
                        "sourceUrl": f"https://homeportal.kz/ru/projects/{record_id}",
                        "dataAsOf": None,
                    }
                )
            return candidates, bool(page.get("next_page_url")) or len(rows) > MAX_RESULTS
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AppError(503, "REGISTRY_RESPONSE_INVALID", "Registry schema changed") from None

    def csv_data(self) -> bytes:
        global _csv_cache
        # Only public fixed dataset bytes; synthetic test transports never share this cache.
        if self.transport is None:
            with _cache_lock:
                if _csv_cache and time.monotonic() - _csv_cache[0] < 300:
                    return _csv_cache[1]
        body = self.read("GET", ASHYQ_CSV)
        if self.transport is None:
            with _cache_lock:
                _csv_cache = (time.monotonic(), body)
        return body

    def ashyq_search(self, query: str) -> tuple[list[dict], bool]:
        try:
            rows = csv.DictReader(io.StringIO(self.csv_data().decode("utf-8-sig")))
            required = {
                "id",
                "object_name",
                "builder_name",
                "auth_org_name",
                "address_name",
                "number",
                "sdu_load_date",
            }
            if not required <= set(rows.fieldnames or []):
                raise ValueError()
            words = normalized(query).split()
            candidates = []
            for index, row in enumerate(rows):
                if index >= 15000 or None in row:
                    raise ValueError()
                combined = " ".join(
                    text(row.get(k), 2000)
                    for k in (
                        "object_name",
                        "address_name",
                        "builder_name",
                        "auth_org_name",
                    )
                )
                if not vko(text(row.get("address_name"))) or not all(
                    word in normalized(combined) for word in words
                ):
                    continue
                candidates.append(
                    {
                        "provider": "ashyq",
                        "recordId": text(row.get("id"), 30),
                        "name": text(row.get("object_name")),
                        "address": text(row.get("address_name")),
                        "developer": text(row.get("builder_name")),
                        "developerBin": "",
                        "holder": text(row.get("auth_org_name")),
                        "holderBin": "",
                        "basisLabel": "Запись открытого набора",
                        "reference": text(row.get("number")),
                        "sourceUrl": ASHYQ_PAGE,
                        "dataAsOf": text(row.get("sdu_load_date")),
                    }
                )
                if len(candidates) > MAX_RESULTS:
                    return candidates[:MAX_RESULTS], True
            return candidates, False
        except (ValueError, TypeError, UnicodeError, csv.Error):
            raise AppError(503, "REGISTRY_RESPONSE_INVALID", "Registry schema changed") from None

    def search(self, query: str) -> dict:
        query = query.strip()
        if not 3 <= len(query) <= 100 or not normalized(query):
            raise AppError(422, "REGISTRY_QUERY_INVALID", "Enter the complex name or address")

        def fetch(provider):
            try:
                candidates, limited = getattr(self, provider + "_search")(query)
                return {
                    "provider": "homeportal" if provider == "home" else provider,
                    "status": "ok",
                    "candidates": candidates,
                    "limited": limited,
                }
            except AppError as error:
                return {
                    "provider": "homeportal" if provider == "home" else provider,
                    "status": "unavailable",
                    "errorCode": error.code,
                    "candidates": [],
                    "limited": False,
                }

        with ThreadPoolExecutor(max_workers=2) as pool:
            sources = list(pool.map(fetch, ["home", "ashyq"]))
        return {"checkedAt": utc_now().isoformat(), "sources": sources}

    def detail(self, record_id: str) -> dict:
        if not re.fullmatch(r"[0-9]{1,15}", record_id):
            raise AppError(422, "REGISTRY_RECORD_INVALID", "Invalid registry record")
        body = self.read("GET", HOME_API + "objects-detail/" + record_id)
        try:
            data = json.loads(body)["data"]
            basic = data["basicData"]
            authority = basic["authority"]
            region = basic["region"]
            if region.get("id") != 16 or not vko(text(basic.get("address"))):
                raise ValueError()
            kind = {1: "regional_permit", 2: "guarantee"}.get(authority.get("id"))
            reference = text(basic.get("warranty_number"))
            if not kind or not reference:
                raise ValueError()
            issued = datetime.strptime(basic["issue_date"], "%d.%m.%Y").date()
            companies = data["companyData"]
            developer = companies["developerData"]
            holder = companies["authorizedData"]
            fields = {
                "provider": "homeportal",
                "recordId": record_id,
                "kind": kind,
                "name": text(basic["name"]),
                "address": text(basic["address"]),
                "developer": text(developer["name"]),
                "developerBin": text(developer["bin"]),
                "holder": text(holder["name"]),
                "holderBin": text(holder["bin"]),
                "reference": reference,
                "issuedOn": issued.isoformat(),
                "sourceUrl": f"https://homeportal.kz/ru/projects/{record_id}",
                "responseSha256": hashlib.sha256(body).hexdigest(),
                "checkedAt": utc_now().isoformat(),
            }
            semantic = {
                key: value
                for key, value in fields.items()
                if key not in {"responseSha256", "checkedAt"}
            }
            fields["documentSha256"] = hashlib.sha256(
                json.dumps(semantic, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            return RegistryDocument.model_validate(fields).model_dump(mode="json", by_alias=True)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise AppError(
                422, "REGISTRY_RECORD_UNVERIFIABLE", "Check the official document"
            ) from None
