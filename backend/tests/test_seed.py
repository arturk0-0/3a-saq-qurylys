from app.models.entities import Advertisement, Complex, Developer, Evidence
from app.services.evidence import validate_factor_evidence
from app.services.risk import calculate_risk
from app.services.seed_data import build_demo_seed


def test_seed_is_deterministic_complete_and_fictional():
    seed = build_demo_seed()
    assert seed == build_demo_seed()
    assert len(seed["complexes"]) == 8
    assert len(seed["advertisements"]) == 12
    developers = {row["id"]: Developer.model_validate(row) for row in seed["developers"]}
    complexes = {row["id"]: Complex.model_validate(row) for row in seed["complexes"]}
    ads = {row["id"]: Advertisement.model_validate(row) for row in seed["advertisements"]}
    evidence = {row["id"]: Evidence.model_validate(row) for row in seed["evidence"]}
    for collection in seed.values():
        assert len({row["id"] for row in collection}) == len(collection)
        assert all(row["demo"] for row in collection)
    for complex_ in complexes.values():
        assert complex_.developer_id in developers
        assert "DEMO" in complex_.name and "DEMO" in complex_.address
        for factor in complex_.factors:
            if factor.status == "confirmed":
                validate_factor_evidence(
                    factor.code, complex_, [evidence[eid] for eid in factor.evidence_ids]
                )
    for ad in ads.values():
        assert ad.complex_id in complexes
        assert ad.source_url.host == "demo.invalid"
    for item in evidence.values():
        assert item.complex_id in complexes
        if item.advertisement_id:
            assert ads[item.advertisement_id].complex_id == item.complex_id


def test_seed_scenarios():
    complexes = [Complex.model_validate(row) for row in build_demo_seed()["complexes"]]
    expected = {"A": (35, "YELLOW"), "B": (70, "RED"), "C": (10, "GREEN")}
    for complex_ in complexes[:3]:
        result = calculate_risk(complex_.factors)
        assert (result.score, result.zone) == expected[complex_.scenario]
    assert complexes[0].factors[0].status == "unknown"
    assert complexes[2].legal_basis.type == "guarantee"
    assert complexes[2].factors[0].status == "unknown"
