"""Drone-photo observations, deliberately separate from legal advertisement risk."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from app.models.common import DomainModel, Identifier, ShortText, utc_now

Visibility = Literal["visible", "not_visible", "uncertain"]


class DroneCriterion(DomainModel):
    id: Identifier
    label: ShortText
    source_url: HttpUrl | None = None

    @model_validator(mode="after")
    def safe_reference(self):
        if self.source_url and (self.source_url.username or self.source_url.password):
            raise ValueError("Credentials are not permitted in a reference URL")
        return self


DEFAULT_CHECKLIST = [
    DroneCriterion(id="fence", label="Видимое ограждение строительной площадки"),
    DroneCriterion(id="signs", label="Различимые знаки и обозначения безопасности"),
    DroneCriterion(id="waste", label="Обозначенное место или контейнер для строительных отходов"),
]


class CreateInspection(DomainModel):
    request_id: UUID
    title: ShortText
    complex_id: Identifier | None = None
    captured_at: AwareDatetime | None = None
    checklist: list[DroneCriterion] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_context(self):
        if len({c.id for c in self.checklist}) != len(self.checklist):
            raise ValueError("Duplicate checklist identifiers")
        if self.captured_at and self.captured_at > utc_now():
            raise ValueError("Photo date cannot be in the future")
        return self


class DroneObservation(DomainModel):
    criterion_id: Identifier
    visibility: Visibility
    explanation: str = Field(min_length=1, max_length=1500, pattern=r"\S")


class DroneResult(DomainModel):
    observations: list[DroneObservation] = Field(min_length=1, max_length=8)
    summary: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    limitations: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class AnalyzeInspection(DomainModel):
    request_id: UUID
    expected_version: int = Field(ge=1)


class ReviewInspection(DomainModel):
    expected_version: int = Field(ge=1)
    run_id: Identifier
    decision: Literal["accepted", "needs_followup", "rejected"]
    notes: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class DronePhoto(DomainModel):
    id: Identifier
    storage_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(gt=0, le=6 * 1024 * 1024)
    uploaded_at: AwareDatetime


class DroneReview(DomainModel):
    run_id: Identifier
    decision: Literal["accepted", "needs_followup", "rejected"]
    notes: str = Field(min_length=1, max_length=2000)
    reviewer: str
    reviewed_at: AwareDatetime


class DroneInspection(DomainModel):
    id: Identifier
    workspace_scope: Literal["demo", "live"]
    title: ShortText
    complex_id: Identifier | None = None
    complex_name: str | None = None
    captured_at: AwareDatetime | None = None
    checklist: list[DroneCriterion] = Field(min_length=1, max_length=8)
    photo: DronePhoto | None = None
    created_at: AwareDatetime
    created_by: str
    fingerprint: str
    version: int = Field(default=1, ge=1)
    status: Literal["awaiting_photo", "ready", "analyzing", "analyzed", "failed", "reviewed"] = (
        "awaiting_photo"
    )
    latest_run_id: Identifier | None = None
    analysis_count: int = Field(default=0, ge=0, le=20)
    last_error: str | None = None
    reviews: list[DroneReview] = Field(default_factory=list, max_length=20)
