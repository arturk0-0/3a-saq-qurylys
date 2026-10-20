"""Narrow public Homeportal projection, using the bounded registry HTTP reader."""

import hashlib
import json
import re
from datetime import datetime
from math import isfinite

from pydantic import HttpUrl, TypeAdapter, ValidationError

from app.core.errors import AppError
from app.models.common import utc_now
from app.models.companies import FactSource, ProjectParty, SourceProject
from app.models.entities import Coordinates
from app.services.registries import HOME_API, RegistryClient, normalized, text

# Generous municipal envelopes reject zero/default points and points in other cities.
# They do NOT certify parcel-level accuracy. No geocoding of company offices.
CITY_BOUNDS = {
    "Усть-Каменогорск": (49.7, 50.2, 82.3, 83.0),
    "Риддер": (50.2, 50.5, 83.3, 83.7),
    "Алтай": (49.5, 49.9, 84.1, 84.5),
    "Серебрянск": (49.55, 49.9, 83.1, 83.5),
    "Шемонаиха": (50.5, 50.75, 81.75, 82.1),
    "Зайсан": (47.35, 47.6, 84.65, 85.1),
}


def source_date(value):
    try:
        result = datetime.strptime(value, "%d.%m.%Y").date()
        return result.isoformat() if result <= utc_now().date() else None
    except (ValueError, TypeError):
        return None


class CompanyRegistry:
    def __init__(self, client: RegistryClient | None = None):
        self.client = client or RegistryClient()

    def project(self, record_id: str) -> SourceProject:
        if not re.fullmatch(r"[0-9]{1,15}", record_id):
            raise AppError(422, "REGISTRY_RECORD_INVALID", "Invalid public record")
        body = self.client.read("GET", HOME_API + "objects-detail/" + record_id)
        try:
            data = json.loads(body)["data"]
            basic = data["basicData"]
            if basic["region"]["id"] != 16:
                raise ValueError()
            city_name = normalized(text(basic["city"]["name_ru"]))
            city = next((key for key in CITY_BOUNDS if normalized(key) in city_name), None)
            if not city:
                raise ValueError()
            parties = []
            for key, role in [
                ("developerData", "developer"),
                ("authorizedData", "authorized_company"),
            ]:
                row = data["companyData"].get(key)
                if row is None or row == {}:
                    # Absence is unknown, never a copy of the developer.
                    continue
                website = text(row.get("develpoer_website"))
                if website and not website.startswith(("https://", "http://")):
                    website = ""
                if website:
                    try:
                        parsed = TypeAdapter(HttpUrl).validate_python(website)
                        if parsed.username or parsed.password or len(str(parsed)) > 500:
                            website = ""
                    except ValidationError:
                        website = ""
                parties.append(
                    ProjectParty(
                        bin=row["bin"], name=row["name"], website=website or None, role=role
                    )
                )
            coordinates, coordinate_status = None, "unavailable"
            location = data.get("locationData") or {}
            try:
                lat, lon = float(location["latitude"]), float(location["longitude"])
                south, north, west, east = CITY_BOUNDS[city]
                if (
                    isfinite(lat)
                    and isfinite(lon)
                    and south <= lat <= north
                    and west <= lon <= east
                ):
                    coordinates = Coordinates(latitude=lat, longitude=lon)
                    coordinate_status = "source_point"
                else:
                    coordinate_status = "outside_city"
            except (KeyError, ValueError, TypeError):
                pass
            # Only an explicitly registered commissioning act counts as an observed act.
            act_date = source_date(basic.get("act_date"))
            reg_date = source_date(basic.get("act_registration_date"))
            act = text(basic.get("act_number"))
            registration = text(basic.get("act_registration_number"))
            has_act = bool(
                act_date
                and reg_date
                and reg_date >= act_date
                and act
                and registration
                and act != "-"
                and registration != "-"
            )
            source = FactSource(
                publisher="Homeportal · КЖК",
                url=f"https://homeportal.kz/ru/projects/{record_id}",
                retrieved_at=utc_now(),
                response_sha256=hashlib.sha256(body).hexdigest(),
            )
            stage, stage_source = ("commissioned", source) if has_act else (None, None)
            if not has_act:
                try:
                    catalog = self.client.catalog_data(basic["name"])
                    rows = json.loads(catalog)["data"]["objects"]["data"]
                    if (
                        isinstance(rows, list)
                        and len(rows) <= 100
                        and any(
                            isinstance(row, dict) and str(row.get("id")) == record_id
                            for row in rows[:20]
                        )
                    ):
                        stage, stage_source = (
                            "under_construction",
                            source.model_copy(
                                update={"response_sha256": hashlib.sha256(catalog).hexdigest()}
                            ),
                        )
                except (AppError, ValueError, KeyError, TypeError):
                    pass  # Parties remain useful when catalog membership cannot be checked.
            fields = dict(
                stage=stage,
                stage_source=stage_source,
                record_id=record_id,
                name=basic["name"],
                address=basic["address"],
                city=city,
                parties=parties,
                coordinates=coordinates,
                coordinate_status=coordinate_status,
                commissioning_reference=f"{act}; регистрация {registration}" if has_act else None,
                commissioning_date=act_date if has_act else None,
            )
            semantic = {
                key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
                for key, value in fields.items()
                if key not in {"parties", "stage_source"}
            }
            semantic["parties"] = [party.model_dump(mode="json") for party in parties]
            fingerprint = hashlib.sha256(
                json.dumps(semantic, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            return SourceProject(
                **fields,
                document_sha256=fingerprint,
                source=FactSource(
                    publisher="Homeportal · КЖК",
                    url=f"https://homeportal.kz/ru/projects/{record_id}",
                    retrieved_at=utc_now(),
                    response_sha256=hashlib.sha256(body).hexdigest(),
                ),
            )
        except (ValueError, KeyError, TypeError, AttributeError, StopIteration, ValidationError):
            raise AppError(
                422, "COMPANY_SOURCE_INVALID", "Public project cannot be verified"
            ) from None
