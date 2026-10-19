"""Public-source company facts, separate from reviewed legal/risk decisions."""

from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl

from app.models.common import DomainModel, ShortText
from app.models.entities import Coordinates
from app.models.provenance import FactSource


class CompanyFact(DomainModel):
    field: Literal["name", "bin", "registrationDate", "status", "legalAddress", "website"]
    value: ShortText
    source: FactSource
    status: Literal["source_reported"] = "source_reported"


class ProjectParty(DomainModel):
    bin: str = Field(pattern=r"^[0-9]{12}$")
    name: ShortText
    website: HttpUrl | None = None
    role: Literal["developer", "authorized_company"]


class SourceProject(DomainModel):
    record_id: str = Field(pattern=r"^[0-9]{1,15}$")
    name: ShortText
    address: ShortText
    city: Literal["Усть-Каменогорск", "Риддер", "Алтай", "Серебрянск", "Шемонаиха", "Зайсан"]
    parties: list[ProjectParty] = Field(min_length=1, max_length=2)
    source: FactSource
    coordinates: Coordinates | None = None
    stage: Literal["under_construction", "commissioned"] | None = None
    stage_source: FactSource | None = None
    coordinate_status: Literal["source_point", "unavailable", "outside_city"]
    # A planned completion date/guarantee is not evidence of commissioning.
    commissioning_reference: str | None = None
    commissioning_date: str | None = None
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SaveSourceProject(DomainModel):
    expected_version: int = Field(ge=0)
    expected_document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    import_to_registry: bool = False


class RefreshCompany(DomainModel):
    expected_version: int = Field(ge=1)


class CompanyRecord(DomainModel):
    id: str = Field(pattern=r"^bin-[0-9]{12}$")
    bin: str = Field(pattern=r"^[0-9]{12}$")
    name: ShortText
    demo: Literal[False] = False
    facts: list[CompanyFact] = Field(default_factory=list, max_length=150)
    projects: list[SourceProject] = Field(default_factory=list, max_length=50)
    version: int = Field(default=1, ge=1)
    updated_at: AwareDatetime
    last_attempt_at: AwareDatetime | None = None
    last_error: str | None = None
