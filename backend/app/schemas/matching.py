from typing import Literal

from pydantic import Field

from app.models.common import DomainModel, Identifier, ShortText


class ComplexCandidate(DomainModel):
    complex_id: Identifier
    name: ShortText
    city: ShortText
    matched_by: Literal["name", "alias", "partial_name"]
    matched_name: ShortText
    demo: bool


class CandidateGroup(DomainModel):
    mention: ShortText
    ambiguous: bool
    candidate_count: int = Field(ge=0, le=500)
    candidates_limited: bool
    candidates: list[ComplexCandidate] = Field(max_length=10)


class MatchingCandidates(DomainModel):
    run_id: Identifier
    advertisement_id: Identifier
    current_complex_id: Identifier
    catalog_limited: bool
    groups: list[CandidateGroup] = Field(max_length=10)
