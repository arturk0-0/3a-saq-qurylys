from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from app.models.common import DomainModel, Identifier


class FactorCode(StrEnum):
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"
    R6 = "R6"


class VerificationStatus(StrEnum):
    UNKNOWN = "unknown"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class RiskZone(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class RiskFactor(DomainModel):
    code: FactorCode
    status: VerificationStatus = VerificationStatus.UNKNOWN
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=30)
    reviewer: str | None = Field(default=None, min_length=1, max_length=128)
    reviewed_at: AwareDatetime | None = None
    notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def require_review_for_confirmation(self) -> Self:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Evidence references must be unique")
        if self.status == VerificationStatus.CONFIRMED and (
            not self.evidence_ids or not self.reviewer or self.reviewed_at is None
        ):
            raise ValueError("Confirmed factors require evidence, reviewer and review time")
        return self


class FactorContribution(DomainModel):
    code: FactorCode
    status: VerificationStatus
    weight: int
    points: int
    evidence_ids: list[Identifier]


class RiskResult(DomainModel):
    score: int = Field(ge=0, le=100)
    zone: RiskZone
    factors: list[FactorContribution]
