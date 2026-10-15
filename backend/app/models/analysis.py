from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.models.common import DomainModel, Identifier, ShortText


class ExtractedHypothesis(DomainModel):
    code: Literal["R2", "R3"]
    quote: str = Field(min_length=1, max_length=2000)
    explanation: ShortText
    confidence: float | None = Field(default=None, ge=0, le=1)


class Extraction(DomainModel):
    hypotheses: list[ExtractedHypothesis] = Field(max_length=6)
    mentioned_complexes: list[ShortText] = Field(max_length=10)
    payment_terms: list[ShortText] = Field(max_length=10)
    uncertainty: str = Field(min_length=1, max_length=2000)


class AnalysisRequest(DomainModel):
    request_id: UUID
    expected_version: int = Field(ge=1)
    screenshot_id: Identifier | None = None


class Hypothesis(ExtractedHypothesis):
    id: Identifier
    run_id: Identifier
    complex_id: Identifier
    advertisement_id: Identifier
    evidence_id: Identifier
    status: Literal["proposed", "accepted", "rejected"] = "proposed"
    model: ShortText
    prompt_version: str
    input_sha256: str
    reviewer: str | None = None
    reviewed_at: AwareDatetime | None = None
    notes: str = ""
    created_at: AwareDatetime
    demo: bool = True
    version: int = 1


class HypothesisDecision(DomainModel):
    decision: Literal["accepted", "rejected"]
    expected_version: int = Field(ge=1)
    notes: str = Field(min_length=1, max_length=2000, pattern=r"\S")
