"""Optional secondary directory: registration date only, matched to the exact BIN.

No directors, founders, contacts or provider scores are collected. The fixed public
HTML page is read with the existing byte/time limits, without redirects or scripts.
"""

import hashlib
import json
import re
from datetime import datetime

from app.core.errors import AppError
from app.models.common import utc_now
from app.models.companies import CompanyFact
from app.models.provenance import FactSource
from app.services.registries import RegistryClient


class CompanyDirectory:
    def __init__(self, client: RegistryClient):
        self.client = client

    def registration(self, bin_: str) -> CompanyFact:
        if not re.fullmatch(r"[0-9]{12}", bin_):
            raise AppError(422, "COMPANY_BIN_INVALID", "Invalid BIN")
        url = "https://pk.adata.kz/company/" + bin_
        try:
            body = self.client.read("GET", url)
            match = re.search(
                rb'<script\b[^>]*\bid="__NUXT_DATA__"[^>]*>(.*?)</script>', body, re.S
            )
            nodes = json.loads(match[1]) if match else None
            if not isinstance(nodes, list) or len(nodes) > 50_000:
                raise ValueError()

            def resolve(index):
                for _ in range(12):
                    if type(index) is not int or not 0 <= index < len(nodes):
                        return None
                    value = nodes[index]
                    if (
                        isinstance(value, list)
                        and len(value) == 2
                        and value[0] in ("Ref", "ShallowRef", "Reactive", "ShallowReactive")
                    ):
                        index = value[1]
                    else:
                        return value
                return None

            dates = set()
            for node in nodes:
                if isinstance(node, dict) and "bin" in node and "reg_date" in node:
                    if resolve(node["bin"]) != bin_:
                        continue
                    raw = resolve(node["reg_date"])
                    # Observed SSR value: DD-MM-YYYY (age); never infer from BIN/age.
                    date_match = re.fullmatch(
                        r"(\d{2}-\d{2}-\d{4})(?:\s+\([^\n]{0,100}\))?", raw or ""
                    )
                    if date_match:
                        value = datetime.strptime(date_match[1], "%d-%m-%Y").date()
                        if value <= utc_now().date():
                            dates.add(value.isoformat())
            if len(dates) != 1:
                raise ValueError()
            return CompanyFact(
                field="registrationDate",
                value=dates.pop(),
                source=FactSource(
                    publisher="ADATA · открытый справочник",
                    url=url,
                    retrieved_at=utc_now(),
                    response_sha256=hashlib.sha256(body).hexdigest(),
                ),
            )
        except (AppError, ValueError, TypeError, KeyError, RecursionError):
            raise AppError(
                503, "COMPANY_DIRECTORY_UNAVAILABLE", "Registration date could not be verified"
            ) from None
