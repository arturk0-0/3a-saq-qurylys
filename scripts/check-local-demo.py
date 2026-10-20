"""Check only a localhost demo: no cloud credentials, third-party libraries or AI calls."""

import argparse
import json
import struct
import zlib
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        parser.error("Only a local HTTP demonstration can be checked")
    base = args.url.rstrip("/")
    token = ""

    def call(
        path, payload=None, method="GET", expected=200, raw=None, mime=None, auth=True
    ):
        headers = {"Authorization": "Bearer " + token} if token and auth else {}
        if payload is not None:
            raw = json.dumps(payload).encode()
            mime = "application/json"
        if mime:
            headers["Content-Type"] = mime
        request = Request(base + path, data=raw, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=90)
        except HTTPError as error:
            response = error
        data = response.read()
        if response.code != expected:
            raise AssertionError(
                f"{method} {path}: {response.code}, expected {expected}"
            )
        # 204 has no response body, even when a framework leaves a JSON media header.
        if response.code == 204 or not data:
            return b""
        return (
            json.loads(data)
            if "application/json" in response.headers.get("Content-Type", "")
            else data
        )

    assert call("/api/local-demo/info")["mode"] == "local-demo"
    call("/api/v1/me", expected=401)
    token = call(
        "/api/local-demo/session",
        {"email": "analyst@example.test", "password": "demo-demo"},
        "POST",
    )["token"]
    assert call("/api/v1/me")["role"] == "analyst"
    rows = call("/api/v1/complexes")["items"]
    assert len(rows) >= 8
    assert {r["id"]: r["risk"]["score"] for r in rows}["demo-complex-02"] == 70
    assert call("/api/v1/companies")["items"]
    assert call("/api/v1/monitoring/items")["items"]

    # Use a new fictional complex so repeated checks never reset anyone's decisions.
    complex_ = call(
        "/api/v1/complexes",
        {
            "name": "DEMO — локальная проверка " + uuid4().hex[:8],
            "city": "Усть-Каменогорск",
            "address": "DEMO — несуществующий адрес",
            "developerId": "demo-developer-01",
        },
        "POST",
        201,
    )
    cid = complex_["id"]
    ad = call(
        "/api/v1/advertisements",
        {
            "complexId": cid,
            "platform": "DEMO local",
            "account": "DEMO — вымышленный аккаунт",
            "sourceUrl": "https://demo.invalid/local/" + uuid4().hex,
            "text": "DEMO — строящийся дом. Внесите депозит. Вымышленное объявление.",
            "publishedAt": datetime.now(UTC).isoformat(),
        },
        "POST",
        201,
    )
    run = call(
        f"/api/v1/advertisements/{ad['id']}/analyze",
        {"requestId": str(uuid4()), "expectedVersion": ad["version"]},
        "POST",
    )
    assert run["model"] == "local-demo-rules-not-gemini"
    assert call(f"/api/v1/complexes/{cid}")["risk"]["score"] == 0
    hypotheses = call(f"/api/v1/advertisements/{ad['id']}/hypotheses")["items"]
    evidence = []
    for hypothesis in hypotheses:
        item = call(
            f"/api/v1/evidence/{hypothesis['evidenceId']}/decision",
            {
                "expectedVersion": 1,
                "decision": "confirmed",
                "notes": "DEMO — источник проверен в локальном сценарии",
                "paymentOfferVerified": hypothesis["code"] == "R2",
                "activeAdvertisingVerified": hypothesis["code"] == "R3",
                "constructionVerified": hypothesis["code"] == "R3",
            },
            "POST",
        )
        evidence.append(item)
        current = call(f"/api/v1/complexes/{cid}")
        call(
            f"/api/v1/complexes/{cid}/factors/decision",
            {
                "code": hypothesis["code"],
                "decision": "confirmed",
                "evidenceIds": [item["id"]],
                "expectedVersion": current["version"],
                "notes": "DEMO — фактор подтверждён человеком",
            },
            "POST",
        )
    current = call(f"/api/v1/complexes/{cid}")
    assert current["risk"]["score"] == 35
    signal = call(
        "/api/v1/signals",
        {
            "complexId": cid,
            "expectedComplexVersion": current["version"],
            "title": "DEMO — локальный отчёт",
            "reason": "Вымышленный пример для проверки запуска",
        },
        "POST",
        201,
    )
    for action in ["submit", "return", "submit", "confirm"]:
        signal = call(
            f"/api/v1/signals/{signal['id']}/decision",
            {
                "expectedVersion": signal["version"],
                "action": action,
                "notes": "DEMO — проверено",
            },
            "POST",
        )
    assert signal["status"] == "confirmed"
    pdf = call(f"/api/v1/signals/{signal['id']}/report")
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1000
    assert len(call(f"/api/v1/signals/{signal['id']}/history")["items"]) == 5

    # Make an ordinary static PNG using only the Python standard library.
    def chunk(tag, content):
        return (
            struct.pack(">I", len(content))
            + tag
            + content
            + struct.pack(">I", zlib.crc32(tag + content))
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * 48) * 16))
        + chunk(b"IEND", b"")
    )
    uploaded = call(
        f"/api/v1/advertisements/{ad['id']}/screenshots?expected_version=1",
        method="POST",
        expected=201,
        raw=png,
        mime="image/png",
    )
    path = f"/api/v1/evidence/{uploaded['id']}/file"
    assert call(path) == png
    call(path, expected=401, auth=False)
    call("/api/local-demo/session", method="DELETE", expected=204)
    call("/api/v1/me", expected=401)
    print(
        "PASS: local login, catalog, monitoring, companies, review, score 35, signal, PDF, private upload, logout"
    )


if __name__ == "__main__":
    main()
