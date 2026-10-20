"""The local judge mode is isolated, persistent and never a production auth fallback."""

import io
import runpy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from local_demo.app import create_local_app
from local_demo.storage import LocalStore


@pytest.fixture
def demo(tmp_path, monkeypatch):
    # Any accidental external integration would fail, even with developer keys set.
    def forbidden(*args, **kwargs):
        raise AssertionError("The offline demo attempted an external request")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setenv("GEMINI_API_KEY", "unused-developer-binding")
    monkeypatch.setenv("SEARCHAPI_API_KEY", "unused-developer-binding")
    app = create_local_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        result = client.post(
            "/api/local-demo/session",
            json={"email": "analyst@example.test", "password": "demo-demo"},
        )
        assert result.status_code == 200
        client.headers["Authorization"] = "Bearer " + result.json()["token"]
        yield client, app, tmp_path


def test_demo_auth_host_origin_and_production_isolation(demo):
    client, _, _ = demo
    assert client.get("/api/v1/me").json()["displayName"] == "Аналитик DEMO"
    assert (
        client.get("/api/v1/me", headers={"Authorization": "Bearer qa-local-analyst"}).status_code
        == 401
    )
    assert client.get("/api/v1/me", headers={"Host": "public.example"}).status_code == 403
    assert client.get("/api/v1/me", headers={"Origin": "https://public.example"}).status_code == 403
    assert client.delete("/api/local-demo/session").status_code == 204
    assert client.get("/api/v1/me").status_code == 401
    with TestClient(create_app(Settings(_env_file=None, firebase_enabled=False))) as production:
        assert production.post("/api/local-demo/session", json={}).status_code == 404
        assert production.get("/api/v1/me").status_code == 401


def test_demo_refuses_cloud_run(tmp_path, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "saq-qurylys-api")
    with pytest.raises(RuntimeError, match="Cloud Run"):
        create_local_app(tmp_path)


def test_demo_persistence_rollbacks_and_scoring(demo):
    client, app, root = demo
    rows = client.get("/api/v1/complexes").json()["items"]
    assert len(rows) == 8
    scores = {r["id"]: r["risk"]["score"] for r in rows}
    assert [scores[f"demo-complex-{i:02}"] for i in [1, 2, 3]] == [35, 70, 10]
    store = app.state.local_workspace.store

    def interrupted(tx):
        tx.set("demoChecks", "rollback", {"id": "rollback"})
        raise ValueError("Simulated interrupted transaction")

    with pytest.raises(ValueError):
        store.atomic(interrupted)
    assert LocalStore(root, {}).get("demoChecks", "rollback") is None
    store.atomic(lambda tx: tx.create("demoChecks", "saved", {"id": "saved"}))
    assert LocalStore(root, {}).get("demoChecks", "saved") == {"id": "saved"}


def test_demo_analysis_collectors_companies_and_uploaded_file(demo):
    client, _, _ = demo
    collected = client.get("/api/v1/monitoring/items").json()["items"]
    assert len(collected) == 1 and "вымышленная" in collected[0]["text"]
    result = client.post(
        "/api/v1/advertisements/demo-ad-01/analyze",
        json={"requestId": str(uuid4()), "expectedVersion": 1},
    )
    assert result.status_code == 200, result.text
    assert result.json()["model"] == "local-demo-rules-not-gemini"
    assert "Не результат ИИ" in result.json()["extraction"]["uncertainty"]
    assert client.get("/api/v1/companies").json()["items"]
    # The API really decodes, validates and privately downloads the exact image.
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(image, format="PNG")
    uploaded = client.post(
        "/api/v1/advertisements/demo-ad-01/screenshots?expected_version=1",
        content=image.getvalue(),
        headers={"Content-Type": "image/png"},
    )
    assert uploaded.status_code == 201, uploaded.text


def test_judge_smoke_completes_full_scenario_including_empty_logout(demo, monkeypatch, capsys):
    client, _, _ = demo
    client.headers.clear()
    script = Path(__file__).resolve().parents[2] / "scripts/check-local-demo.py"
    namespace = runpy.run_path(str(script))
    main = namespace["main"]

    def local_request(request, timeout):
        response = client.request(
            request.get_method(),
            request.full_url,
            content=request.data,
            headers=dict(request.header_items()),
        )
        return SimpleNamespace(
            code=response.status_code, headers=response.headers, read=lambda: response.content
        )

    monkeypatch.setitem(main.__globals__, "urlopen", local_request)
    monkeypatch.setattr("sys.argv", [str(script)])
    main()
    assert "PASS: local login" in capsys.readouterr().out
