from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl

from app.models.common import DomainModel, Identifier, ShortText


class FactSource(DomainModel):
    publisher: ShortText
    url: HttpUrl
    retrieved_at: AwareDatetime
    effective_date: str | None = None
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PartySnapshot(DomainModel):
    company_id: Identifier
    name: ShortText
    bin: str = Field(pattern=r"^[0-9]{12}$")
    role: Literal["developer", "authorized_company"]
    source: FactSource
