"""Guards for opt-in local tests, never imported by production application code."""

import re


def validate_target(host: str, project: str, *, opt_in: str) -> None:
    if opt_in != "1":
        raise ValueError("Set SAQ_FIRESTORE_INTEGRATION=1 only for the local test runner")
    match = re.fullmatch(r"127\.0\.0\.1:([0-9]{1,5})", host)
    if match is None or not 1 <= int(match[1]) <= 65535:
        raise ValueError("Firestore integration tests require an explicit IPv4 loopback port")
    if not re.fullmatch(r"demo-saq-it-[a-z0-9-]{1,30}", project):
        raise ValueError("Firestore integration tests require a disposable demo-saq-it project")
