from collections.abc import Sequence

from app.models.entities import Complex, Evidence
from app.models.risk import FactorCode, VerificationStatus


def validate_factor_evidence(
    code: FactorCode, complex_: Complex, evidence: Sequence[Evidence]
) -> None:
    """Require reviewed, correctly linked evidence for the actual legal condition."""
    if not evidence or any(
        item.complex_id != complex_.id
        or item.status != VerificationStatus.CONFIRMED
        or item.demo != complex_.demo
        for item in evidence
    ):
        raise ValueError("Select verified evidence from this complex and data scope")
    checks = {
        FactorCode.R1: lambda e: (
            e.type == "legal_basis_review"
            and e.legal_absence_verified
            and e.applicable_bases_checked
        ),
        FactorCode.R2: lambda e: (
            e.type in {"advertisement", "screenshot"}
            and e.payment_offer_verified
            and e.advertisement_id is not None
        ),
        FactorCode.R3: lambda e: (
            e.type in {"advertisement", "screenshot"}
            and e.active_advertising_verified
            and e.construction_verified
        ),
        FactorCode.R4: lambda e: e.type == "complaint" and e.collective_complaint_verified,
        FactorCode.R5: lambda e: (
            e.type == "progress_report"
            and e.claimed_percent is not None
            and e.verified_percent is not None
            and abs(e.claimed_percent - e.verified_percent) >= 20
            and e.claimed_at is not None
            and e.verified_at is not None
            and bool(e.claimed_source.strip())
            and bool(e.verified_source.strip())
        ),
        FactorCode.R6: lambda e: e.type == "work_status" and e.work_stoppage_verified,
    }
    if code == FactorCode.R1 and complex_.legal_basis.status == "confirmed":
        raise ValueError("Confirmed applicable legal basis excludes R1; review the basis first")
    if code == FactorCode.R3 and complex_.stage != "under_construction":
        raise ValueError("R3 applies only to housing under construction")
    if not any(checks[code](item) for item in evidence):
        raise ValueError(f"Evidence does not establish the required condition for {code}")
