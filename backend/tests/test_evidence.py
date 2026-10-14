from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.entities import Complex, Evidence
from app.models.risk import FactorCode
from app.services.evidence import validate_factor_evidence
from app.services.seed_data import build_demo_seed

NOW = datetime(2026, 10, 14, tzinfo=UTC)


@pytest.fixture
def complex_():
    return Complex.model_validate(build_demo_seed()["complexes"][0])


def evidence(complex_, **overrides):
    return Evidence(
        **{
            "id": "evidence-1",
            "complex_id": complex_.id,
            "type": "document",
            "source_reference": "Review document 1",
            "excerpt": "Documentary evidence",
            "captured_at": NOW,
            "status": "confirmed",
            "reviewer": "analyst-1",
            "reviewed_at": NOW,
            **overrides,
        }
    )


def test_missing_registry_result_does_not_establish_r1(complex_):
    item = evidence(complex_, type="legal_basis_review", excerpt="Not found in registry")
    with pytest.raises(ValueError, match="does not establish"):
        validate_factor_evidence(FactorCode.R1, complex_, [item])


def test_absence_requires_all_applicable_bases_reviewed(complex_):
    with pytest.raises(ValidationError):
        evidence(complex_, type="legal_basis_review", legal_absence_verified=True)


def test_valid_guarantee_excludes_r1():
    complex_ = Complex.model_validate(build_demo_seed()["complexes"][2])
    item = evidence(
        complex_,
        type="legal_basis_review",
        legal_absence_verified=True,
        applicable_bases_checked=True,
    )
    with pytest.raises(ValueError, match="excludes R1"):
        validate_factor_evidence(FactorCode.R1, complex_, [item])


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "proposed"},
        {"status": "unknown"},
        {"status": "rejected"},
        {"complex_id": "other-complex"},
        {"demo": False},
    ],
)
def test_wrong_or_unverified_evidence_cannot_confirm(complex_, overrides):
    item = evidence(complex_, type="work_status", work_stoppage_verified=True, **overrides)
    with pytest.raises(ValueError):
        validate_factor_evidence(FactorCode.R6, complex_, [item])


@pytest.mark.parametrize(
    "claimed,verified,expected", [(60, 40, True), (59, 40, False), (40, 60, True)]
)
def test_progress_gap_uses_absolute_percentage_points(complex_, claimed, verified, expected):
    item = evidence(
        complex_,
        type="progress_report",
        claimed_percent=claimed,
        verified_percent=verified,
        claimed_at=NOW,
        verified_at=NOW,
        claimed_source="Project presentation",
        verified_source="Inspection report",
    )
    if expected:
        validate_factor_evidence(FactorCode.R5, complex_, [item])
    else:
        with pytest.raises(ValueError):
            validate_factor_evidence(FactorCode.R5, complex_, [item])


def test_progress_without_sources_cannot_confirm(complex_):
    item = evidence(complex_, type="progress_report", claimed_percent=80, verified_percent=20)
    with pytest.raises(ValueError):
        validate_factor_evidence(FactorCode.R5, complex_, [item])


def test_commissioned_housing_cannot_confirm_r3(complex_):
    complex_.stage = "commissioned"
    item = evidence(
        complex_, type="advertisement", active_advertising_verified=True, construction_verified=True
    )
    with pytest.raises(ValueError, match="under construction"):
        validate_factor_evidence(FactorCode.R3, complex_, [item])


def test_evidence_requires_source(complex_):
    with pytest.raises(ValidationError):
        evidence(complex_, source_reference=" ")


@pytest.mark.parametrize("city", ["Семей", "Астана", "Алматы"])
def test_outside_region_cities_are_rejected(complex_, city):
    with pytest.raises(ValidationError):
        Complex.model_validate({**complex_.model_dump(), "city": city})
