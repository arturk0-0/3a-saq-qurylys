import hashlib
import json
from copy import deepcopy
from dataclasses import asdict

import pytest

from app.cli.trace import main
from app.services.ad_trace import (
    MAX_DOCUMENTS,
    MAX_NAMES,
    MAX_OCCURRENCES,
    MAX_PROPOSALS,
    TRACE_VERSION,
    TraceDocument,
    extract_identifiers,
    normalize_domain,
    normalize_phone,
    normalize_whatsapp,
    propose_links,
)


@pytest.mark.parametrize(
    "phone",
    [
        "+7 (000) 000-00-01",
        "8 (000) 000-00-01",
        "70000000001",
        "80000000001",
        "+7\u00a0000\u202f000 00 01",
        "8–000–000–00–01",
    ],
)
def test_phone_variants_have_one_identity(phone):
    assert normalize_phone(phone) == "+70000000001"


@pytest.mark.parametrize(
    "phone",
    [
        "0000001",
        "123456789012",
        "+80000000001",
        "+440000000000",
        "700000000012",
        "tel:+70000000001",
        "7000abc0000001",
        "٧٠٠٠٠٠٠٠٠٠١",
        "7000000000",
        "7\n0000000001",
    ],
)
def test_local_numbers_bins_foreign_numbers_and_text_are_not_guessed(phone):
    assert normalize_phone(phone) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://wa.me/70000000001",
        "wa.me/80000000001?text=DEMO",
        "https://api.whatsapp.com/send?phone=70000000001&text=DEMO",
        "https://www.whatsapp.com/send?phone=%2B70000000001",
    ],
)
def test_whatsapp_links_match_the_phone_in_another_ad(url):
    assert normalize_whatsapp(url) == "+70000000001"
    result = propose_links(
        [TraceDocument("one", "DEMO +7 (000) 000-00-01"), TraceDocument("two", url)]
    )
    match = result.proposals[0].matches[0]
    assert match.kind == "phone"
    assert match.right[0].quote == url
    assert match.right[0].origin == "whatsapp_url"


@pytest.mark.parametrize(
    "url",
    [
        "https://wa.me/message/OPAQUE",
        "https://wa.me.evil.invalid/70000000001",
        "https://api.whatsapp.com/send?phone=70000000001&phone=70000000002",
        "https://api.whatsapp.com/not-send?phone=70000000001",
        "https://wa.me/0000001",
        "https://user@wa.me/70000000001",
        "javascript:wa.me/70000000001",
    ],
)
def test_whatsapp_short_codes_lookalikes_duplicate_parameters_and_credentials_are_rejected(url):
    assert normalize_whatsapp(url) is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://WWW.Example.Invalid:443/path?q=1#hash", "example.invalid"),
        ("example.invalid", "example.invalid"),
        ("https://sales.example.invalid", "sales.example.invalid"),
        ("https://пример.рф/", "xn--e1afmkfd.xn--p1ai"),
        ("https://Example.Invalid./", "example.invalid"),
    ],
)
def test_domains_keep_full_hosts_and_do_not_fetch_urls(url, expected):
    assert normalize_domain(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@example.invalid",
        "file:///tmp/private",
        "http://127.0.0.1",
        "http://[::1]",
        "http://localhost",
        "https://test.local",
        "https://test.internal",
        "https://-invalid.example",
        "https://example.invalid:wrong",
        "http://a_b.invalid",
        "https://example.invalid\n.evil.invalid",
        "https://example.invalid\\@evil.invalid",
    ],
)
def test_unsafe_or_non_domain_inputs_do_not_become_identifiers(url):
    assert normalize_domain(url) is None


def test_exact_unicode_quotes_offsets_and_conservative_alias_matching():
    text = "🛡 DEMO — ЖК «САЯЛЫ-БАҒЫ». Телефон: +7 (000) 000-00-01; example.invalid."
    result = extract_identifiers(text, known_names=["ЖК Саялы бағы", "DEMO ЖК", "дом"])
    assert {item.kind for item in result.occurrences} == {"phone", "domain", "alias"}
    alias = next(item for item in result.occurrences if item.kind == "alias")
    assert alias.normalized == "саялы бағы"
    assert alias.quote == "САЯЛЫ-БАҒЫ"
    assert all(text[item.start : item.end] == item.quote for item in result.occurrences)
    assert not extract_identifiers("Преддомовой участок", known_names=["дом"]).occurrences
    assert not extract_identifiers("Сaялы бағы", known_names=["Саялы бағы"]).occurrences


def test_urls_do_not_leak_query_phone_numbers_and_shared_platforms_are_not_links():
    text = (
        "https://instagram.com/a https://m.instagram.com/b "
        "https://wa.me/message/OPAQUE?text=70000000001 "
        "example.invalid/70000000002 email@example.invalid 150 000 тенге БИН 700000000012"
    )
    items = extract_identifiers(text).occurrences
    assert [(item.kind, item.normalized) for item in items] == [("domain", "example.invalid")]
    assert not propose_links(
        [
            TraceDocument("a", "https://instagram.com/first"),
            TraceDocument("b", "https://instagram.com/second"),
        ]
    ).proposals


def test_multiple_reasons_and_occurrences_produce_one_stable_pair_without_mutations():
    docs = [
        TraceDocument(
            "a",
            "DEMO Учебный берег +7 (000) 000-00-01 +7 (000) 000-00-01 https://www.example.invalid/a",
            2,
        ),
        TraceDocument("b", "DEMO Учебный берег https://wa.me/70000000001 example.invalid/b", 3),
        TraceDocument("c", "DEMO +7 (000) 000-00-02"),
    ]
    before = deepcopy(docs)
    result = propose_links(docs, known_names=["Учебный берег"])
    assert docs == before
    assert result == propose_links(list(reversed(docs)), known_names=["ЖК Учебный берег"])
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert (proposal.left_id, proposal.right_id, proposal.left_version, proposal.right_version) == (
        "a",
        "b",
        2,
        3,
    )
    assert {m.kind for m in proposal.matches} == {"alias", "domain", "phone"}
    assert len(next(m for m in proposal.matches if m.kind == "phone").left) == 2
    assert not proposal.name_only
    assert proposal.left_text_sha256 == hashlib.sha256(docs[0].text.encode()).hexdigest()
    for match in proposal.matches:
        for item in match.left:
            assert docs[0].text[item.start : item.end] == item.quote
        for item in match.right:
            assert docs[1].text[item.start : item.end] == item.quote
    assert result.version == TRACE_VERSION
    assert not result.identifiers_limited and not result.proposals_limited
    # This result carries reasons/provenance, no legal decision or risk score.
    assert not {"score", "zone", "reviewer", "confirmed", "owner"} & asdict(proposal).keys()


def test_alias_only_is_explicitly_weak_and_cross_scope_pairs_are_never_proposed():
    docs = [TraceDocument("a", "Учебный берег"), TraceDocument("b", "ЖК Учебный берег")]
    assert propose_links(docs, known_names=["Учебный берег"]).proposals[0].name_only
    assert not propose_links(
        [docs[0], TraceDocument("b", "Учебный берег", demo=False)], known_names=["Учебный берег"]
    ).proposals
    assert not propose_links([docs[0]]).proposals


def test_edits_change_snapshot_digest_and_missing_information_does_not_prove_a_link():
    a = TraceDocument("a", "+7 (000) 000-00-01", version=1)
    b = TraceDocument("b", "8 (000) 000-00-01")
    old = propose_links([a, b]).proposals[0]
    new = propose_links([TraceDocument("a", a.text + " DEMO", version=2), b]).proposals[0]
    assert old.left_text_sha256 != new.left_text_sha256
    assert old.left_version != new.left_version
    assert not propose_links([TraceDocument("a", "Нет контакта"), b]).proposals


def test_limits_are_visible_and_large_batches_are_rejected_not_silently_scanned():
    result = extract_identifiers(
        " ".join(f"https://site{i}.invalid" for i in range(MAX_OCCURRENCES + 2))
    )
    assert result.limited and len(result.occurrences) == MAX_OCCURRENCES
    docs = [TraceDocument(f"ad-{i:03}", "+7 (000) 000-00-01") for i in range(22)]
    links = propose_links(docs)
    assert links.proposals_limited and len(links.proposals) == MAX_PROPOSALS
    assert links == propose_links(list(reversed(docs)))
    with pytest.raises(ValueError):
        propose_links([TraceDocument(f"ad-{i}", "DEMO") for i in range(MAX_DOCUMENTS + 1)])
    with pytest.raises(ValueError):
        extract_identifiers("x" * 20001)
    with pytest.raises(ValueError):
        propose_links([], known_names=["DEMO"] * (MAX_NAMES + 1))


@pytest.mark.parametrize(
    "docs",
    [
        [TraceDocument("same", "a"), TraceDocument("same", "b")],
        [TraceDocument("bad/path", "a")],
        [TraceDocument("a", "a", version=0)],
        [TraceDocument("a", "a", version=True)],
        [TraceDocument("a", "a", demo=1)],
    ],
)
def test_invalid_identity_or_scope_is_rejected(docs):
    with pytest.raises(ValueError):
        propose_links(docs)


def test_offline_demo_has_one_proposal_and_does_not_instantiate_cloud_clients(capsys, monkeypatch):
    def no_client(*args, **kwargs):
        pytest.fail("Offline trace must not access external providers")

    monkeypatch.setattr("httpx.Client", no_client)
    monkeypatch.setattr("firebase_admin.initialize_app", no_client)
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["demo"] is True
    assert len(output["result"]["proposals"]) == 1
    assert "OFFLINE DEMO" in output["notice"]
