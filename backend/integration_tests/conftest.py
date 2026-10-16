"""Opt-in emulator fixture; never initializes ADC or accepts a real project ID."""

import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from app.repositories.firestore import FirestoreStore
from app.services.seed import import_demo_seed
from app.services.workspace import WorkspaceService
from qa.firestore.safety import validate_target


@pytest.fixture
def db():
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    project = f"demo-saq-it-{uuid4().hex[:12]}"
    try:
        validate_target(host, project, opt_in=os.environ.get("SAQ_FIRESTORE_INTEGRATION", ""))
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)
    client = firestore.Client(project=project, credentials=AnonymousCredentials())
    assert client._emulator_host == host
    # Each disposable namespace receives the repository's actual client rules.
    rules = (Path(__file__).parents[2] / "firestore.rules").read_text()
    with httpx.Client(trust_env=False, timeout=10) as http:
        response = http.put(
            f"http://{host}/emulator/v1/projects/{project}:securityRules",
            json={"rules": {"files": [{"name": "firestore.rules", "content": rules}]}},
        )
        assert response.is_success, "Local emulator must accept the repository rules"
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def workspace(db):
    store = FirestoreStore(db)
    result = import_demo_seed(store, "local-test-admin")
    assert result["created"] == 37
    return WorkspaceService(store)
