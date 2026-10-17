"""Advertising-link persistence with the real SDK in the opt-in local emulator."""

import os
from copy import deepcopy

import httpx
import pytest

from app.core.errors import AppError
from app.models.ad_trace import TraceDecision, TraceSave
from app.models.auth import Principal
from app.models.common import utc_now
from app.schemas.workspace import AdvertisementCreate
from app.services.ad_links import AdLinksService


def test_trace_round_trip_audit_staleness_and_private_client_rules(workspace, db):
    user = Principal(uid="local-trace-reviewer", role="analyst")
    ads = []
    for index, text in enumerate(["DEMO +7 (000) 000-00-01", "DEMO https://wa.me/70000000001"]):
        ads.append(
            workspace.create_advertisement(
                AdvertisementCreate(
                    complex_id="demo-complex-04",
                    platform="DEMO TRACE",
                    account=f"fictional-trace-{index}",
                    source_url=f"https://demo.invalid/trace/{index}",
                    text=text,
                    published_at=utc_now(),
                ),
                user,
            )
        )
    service = AdLinksService(workspace)
    before = deepcopy(workspace.complex("demo-complex-04"))
    candidates = service.candidates(ads[0].id)
    item = next(row for row in candidates["items"] if row["otherAdvertisement"]["id"] == ads[1].id)
    payload = TraceSave(
        other_advertisement_id=ads[1].id,
        expected_version=1,
        expected_other_version=1,
        expected_snapshot_id=item["id"],
    )
    saved = service.save(ads[0].id, payload, user)
    assert service.save(ads[0].id, payload, user) == saved
    confirmed = service.decide(
        saved.id,
        TraceDecision(
            decision="confirmed",
            notes="DEMO совпадение сверено по оригиналам",
            expected_version=1,
        ),
        user,
    )
    assert confirmed.reviewer == user.uid and confirmed.version == 2
    assert workspace.store.get("adLinks", saved.id)["status"] == "confirmed"
    events = workspace.store.list("auditLogs", filters=[("entityId", "==", saved.id)], limit=10)
    assert {row["action"] for row in events} == {"adLink.propose", "adLink.review"}
    assert len(events) == 2
    assert workspace.complex("demo-complex-04") == before
    with pytest.raises(AppError) as error:
        service.decide(
            saved.id, TraceDecision(decision="rejected", notes="Повтор", expected_version=1), user
        )
    assert error.value.status_code == 409
    # A new source version gets a separate immutable match snapshot.
    db.collection("advertisements").document(ads[1].id).update({"version": 2})
    current = next(
        row
        for row in service.candidates(ads[0].id)["items"]
        if row["otherAdvertisement"]["id"] == ads[1].id
    )
    assert current["id"] != saved.id and current["saved"] is None
    proposed = service.save(
        ads[0].id,
        TraceSave(
            other_advertisement_id=ads[1].id,
            expected_version=1,
            expected_other_version=2,
            expected_snapshot_id=current["id"],
        ),
        user,
    )
    db.collection("advertisements").document(ads[1].id).update({"text": "DEMO changed"})
    with pytest.raises(AppError) as error:
        service.decide(
            proposed.id,
            TraceDecision(decision="confirmed", notes="Проверка", expected_version=1),
            user,
        )
    assert error.value.code == "TRACE_STALE"
    assert workspace.store.get("adLinks", proposed.id)["status"] == "proposed"
    host = os.environ["FIRESTORE_EMULATOR_HOST"]
    url = f"http://{host}/v1/projects/{db.project}/databases/(default)/documents/adLinks/{saved.id}"
    with httpx.Client(trust_env=False, timeout=10) as client:
        assert client.get(url).status_code == 403
        assert client.patch(url, json={"fields": {}}).status_code == 403
