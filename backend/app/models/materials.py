"""Additive material workflow; confirmed risk still uses the original R1–R6 models."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.models.common import DomainModel, Identifier


class MaterialDecision(DomainModel):
    hypothesis_id: Identifier
    decision: Literal["confirmed", "rejected", "insufficient"]


class MaterialReview(DomainModel):
    request_id: UUID
    expected_version: int = Field(ge=1)
    revision_id: Identifier
    complex_id: Identifier | None = None
    expected_complex_version: int | None = Field(default=None, ge=1)
    decisions: list[MaterialDecision] = Field(default_factory=list, max_length=30)
    notes: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    disposition: Literal["reviewed", "needs_review", "dismissed"]

    @model_validator(mode="after")
    def unique_decisions(self):
        if len({d.hypothesis_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("Each hypothesis can be decided only once")
        return self


class MaterialRetry(DomainModel):
    request_id: UUID
    expected_version: int = Field(ge=1)
