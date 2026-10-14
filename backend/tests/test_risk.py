from datetime import UTC, datetime
from itertools import combinations

import pytest
from pydantic import ValidationError

from app.models.risk import FactorCode, RiskFactor, RiskZone, VerificationStatus
from app.services.risk import calculate_risk

NOW = datetime(2026, 10, 14, tzinfo=UTC)


def confirmed(code):
    return RiskFactor(
        code=code,
        status="confirmed",
        evidence_ids=["evidence-1"],
        reviewer="analyst-1",
        reviewed_at=NOW,
    )


@pytest.mark.parametrize(
    "codes,score,zone",
    [
        (["R2", "R3"], 35, "YELLOW"),
        (["R1", "R2", "R3"], 70, "RED"),
        (["R3"], 10, "GREEN"),
        (["R1", "R3", "R4"], 60, "YELLOW"),
        (["R2", "R3", "R4", "R5", "R6"], 65, "YELLOW"),
        (["R1", "R2"], 60, "RED"),
        ([], 0, "GREEN"),
        (["R4", "R6"], 20, "GREEN"),
        (["R2"], 25, "YELLOW"),
        (list(FactorCode), 100, "RED"),
    ],
)
def test_official_scenarios_and_boundaries(codes, score, zone):
    result = calculate_risk(confirmed(code) for code in codes)
    assert (result.score, result.zone) == (score, zone)
    assert len(result.factors) == 6
    assert sum(item.points for item in result.factors) == result.score


@pytest.mark.parametrize("status", ["unknown", "proposed", "rejected"])
def test_unconfirmed_hypotheses_never_score(status):
    assert calculate_risk([RiskFactor(code="R1", status=status)]).score == 0


def test_duplicate_factors_are_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        calculate_risk([confirmed("R2"), confirmed("R2")])


@pytest.mark.parametrize("missing", ["evidence_ids", "reviewer", "reviewed_at"])
def test_confirmation_requires_provenance(missing):
    fields = confirmed("R1").model_dump()
    fields.pop(missing)
    with pytest.raises(ValidationError):
        RiskFactor(**fields)


def test_all_factor_combinations_follow_zone_rule_and_order_does_not_matter():
    for length in range(7):
        for codes in combinations(FactorCode, length):
            result = calculate_risk(confirmed(code) for code in codes)
            assert result == calculate_risk(confirmed(code) for code in reversed(codes))
            assert 0 <= result.score <= 100
            if result.zone == RiskZone.RED:
                assert result.score >= 60 and {FactorCode.R1, FactorCode.R2} <= set(codes)
            if result.score < 25:
                assert result.zone == RiskZone.GREEN


def test_rejecting_a_factor_recalculates_score():
    factors = [confirmed("R1"), confirmed("R2"), confirmed("R3")]
    factors[0] = RiskFactor(code="R1", status=VerificationStatus.REJECTED)
    result = calculate_risk(factors)
    assert (result.score, result.zone) == (35, "YELLOW")
