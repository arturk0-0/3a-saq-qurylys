from collections.abc import Iterable
from types import MappingProxyType

from app.models.risk import (
    FactorCode,
    FactorContribution,
    RiskFactor,
    RiskResult,
    RiskZone,
    VerificationStatus,
)

FACTOR_WEIGHTS = MappingProxyType(
    {
        FactorCode.R1: 35,
        FactorCode.R2: 25,
        FactorCode.R3: 10,
        FactorCode.R4: 15,
        FactorCode.R5: 10,
        FactorCode.R6: 5,
    }
)


def calculate_risk(factors: Iterable[RiskFactor]) -> RiskResult:
    """Score only reviewed facts, once per factor; never infer facts from missing data."""
    by_code: dict[FactorCode, RiskFactor] = {}
    for factor in factors:
        if factor.code in by_code:
            raise ValueError(f"Duplicate risk factor: {factor.code}")
        by_code[factor.code] = factor
    contributions: list[FactorContribution] = []
    confirmed: set[FactorCode] = set()
    for code, weight in FACTOR_WEIGHTS.items():
        factor = by_code.get(code, RiskFactor(code=code))
        if factor.status == VerificationStatus.CONFIRMED:
            confirmed.add(code)
        contributions.append(
            FactorContribution(
                code=code,
                status=factor.status,
                weight=weight,
                points=weight if code in confirmed else 0,
                evidence_ids=factor.evidence_ids,
            )
        )
    score = min(100, sum(item.points for item in contributions))
    zone = RiskZone.GREEN if score < 25 else RiskZone.YELLOW
    if score >= 60 and {FactorCode.R1, FactorCode.R2} <= confirmed:
        zone = RiskZone.RED
    return RiskResult(score=score, zone=zone, factors=contributions)
