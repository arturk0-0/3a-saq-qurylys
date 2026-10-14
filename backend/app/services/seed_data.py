"""Deterministic fictional data. Never touches Firestore during import or application startup."""

from datetime import UTC, datetime

from app.models.entities import Advertisement, Complex, Developer, Evidence, LegalBasis, Progress
from app.models.risk import FactorCode, RiskFactor
from app.services.evidence import validate_factor_evidence
from app.services.risk import calculate_risk

SEED_VERSION = "demo-v1"
SEED_REVIEWER = "DEMO-fictional-reviewer"
SEED_DATE = datetime(2026, 10, 14, 8, tzinfo=UTC)
COMPLEXES = (
    ("DEMO — Янтарный берег", "Усть-Каменогорск", "Учебная улица, 101", 49.955, 82.615),
    ("DEMO — Кедровый квартал", "Риддер", "Вымышленный проспект, 102", 50.339, 83.512),
    ("DEMO — Солнечный склон", "Усть-Каменогорск", "Демонстрационная улица, 103", 49.965, 82.630),
    ("DEMO — Горная мозаика", "Алтай", "Учебный переулок, 104", 49.727, 84.274),
    ("DEMO — Тихая долина", "Серебрянск", "Вымышленная улица, 105", 49.681, 83.300),
    ("DEMO — Восточный сад", "Шемонаиха", "Демонстрационный проспект, 106", 50.632, 81.910),
    ("DEMO — Лазурный двор", "Зайсан", "Учебная набережная, 107", 47.467, 84.872),
    ("DEMO — Сосновая терраса", "Риддер", "Вымышленная улица, 108", 50.347, 83.521),
)


def build_demo_seed() -> dict[str, list[dict]]:
    developers: list[Developer] = []
    complexes: list[Complex] = []
    advertisements: list[Advertisement] = []
    evidence: list[Evidence] = []
    for index, (name, city, address, latitude, longitude) in enumerate(COMPLEXES, 1):
        developer = Developer(
            id=f"demo-developer-{index:02d}",
            name=f"DEMO — Учебный застройщик {index}",
            bin=f"0000000000{index:02d}",
        )
        developers.append(developer)
        complex_ = Complex(
            id=f"demo-complex-{index:02d}",
            name=name,
            city=city,
            address=f"DEMO, несуществующий адрес: {address}",
            developer_id=developer.id,
            coordinates={"latitude": latitude, "longitude": longitude},
            progress=Progress(
                claimed_percent=20 + index * 5,
                claimed_at=SEED_DATE,
                claimed_source=f"DEMO-презентация проекта {index}",
            ),
            scenario={1: "A", 2: "B", 3: "C"}.get(index),
            created_at=SEED_DATE,
            updated_at=SEED_DATE,
        )
        if index == 3:
            complex_.legal_basis = LegalBasis(
                type="guarantee",
                status="confirmed",
                reference="DEMO-GUARANTEE-003",
                source="Синтетический документ: применимая действующая гарантия (сценарий C)",
                checked_at=SEED_DATE,
                reviewer=SEED_REVIEWER,
                valid_until=datetime(2027, 12, 31, tzinfo=UTC),
            )
        text = f"DEMO: {name}. Строящийся жилой комплекс в городе {city}."
        if index in {1, 2}:
            text += " Забронируйте квартиру: внесите платный депозит 300 000 тенге."
        else:
            text += " Информация о планировках. Оплата и бронирование не предлагаются."
        advertisement = Advertisement(
            id=f"demo-ad-{index:02d}",
            complex_id=complex_.id,
            platform="DEMO social",
            account=f"demo_training_account_{index}",
            source_url=f"https://demo.invalid/advertisements/{index}",
            text=text,
            published_at=SEED_DATE,
            captured_at=SEED_DATE,
            created_by=SEED_REVIEWER,
        )
        advertisements.append(advertisement)
        ad_evidence = Evidence(
            id=f"demo-evidence-ad-{index:02d}",
            complex_id=complex_.id,
            advertisement_id=advertisement.id,
            type="advertisement",
            source_url=advertisement.source_url,
            excerpt=text,
            captured_at=SEED_DATE,
            status="confirmed",
            reviewer=SEED_REVIEWER,
            reviewed_at=SEED_DATE,
            payment_offer_verified=index in {1, 2},
            active_advertising_verified=True,
            construction_verified=True,
        )
        evidence.append(ad_evidence)
        factors = [RiskFactor(code=code) for code in FactorCode]
        for factor in factors:
            if factor.code == "R3" or (factor.code == "R2" and index in {1, 2}):
                reviewed = RiskFactor(
                    code=factor.code,
                    status="confirmed",
                    evidence_ids=[ad_evidence.id],
                    reviewer=SEED_REVIEWER,
                    reviewed_at=SEED_DATE,
                    notes="Вымышленная DEMO-проверка",
                )
                validate_factor_evidence(reviewed.code, complex_, [ad_evidence])
                factors[factors.index(factor)] = reviewed
        if index == 2:
            legal_evidence = Evidence(
                id="demo-evidence-legal-02",
                complex_id=complex_.id,
                type="legal_basis_review",
                source_reference=(
                    "DEMO-REVIEW-002: синтетическая проверка всех применимых оснований"
                ),
                excerpt="DEMO: документально проверено отсутствие всех применимых оснований. "
                "Это вымышленный сценарий B, не результат поиска в реальном госреестре.",
                captured_at=SEED_DATE,
                status="confirmed",
                reviewer=SEED_REVIEWER,
                reviewed_at=SEED_DATE,
                legal_absence_verified=True,
                applicable_bases_checked=True,
            )
            evidence.append(legal_evidence)
            validate_factor_evidence(FactorCode.R1, complex_, [legal_evidence])
            factors[0] = RiskFactor(
                code="R1",
                status="confirmed",
                evidence_ids=[legal_evidence.id],
                reviewer=SEED_REVIEWER,
                reviewed_at=SEED_DATE,
                notes="DEMO: отсутствие оснований проверено документально",
            )
        complex_.factors = factors
        # Re-validate after assembly; mutation must not bypass model invariants.
        complexes.append(Complex.model_validate(complex_.model_dump()))
    for number in range(9, 13):
        original = advertisements[number - 9]
        advertisements.append(
            Advertisement(
                **{
                    **original.model_dump(),
                    "id": f"demo-ad-{number:02d}",
                    "source_url": f"https://demo.invalid/advertisements/{number}",
                    "text": f"DEMO — дополнительная публикация {number}. {original.text}",
                }
            )
        )
    expected = [(35, "YELLOW"), (70, "RED"), (10, "GREEN")]
    for complex_, scenario in zip(complexes[:3], expected, strict=True):
        risk = calculate_risk(complex_.factors)
        if (risk.score, risk.zone) != scenario:
            raise ValueError("Seed does not match the official scoring scenarios")
    return {
        "developers": [item.model_dump(mode="json", by_alias=True) for item in developers],
        "complexes": [item.model_dump(mode="json", by_alias=True) for item in complexes],
        "advertisements": [item.model_dump(mode="json", by_alias=True) for item in advertisements],
        "evidence": [item.model_dump(mode="json", by_alias=True) for item in evidence],
    }
