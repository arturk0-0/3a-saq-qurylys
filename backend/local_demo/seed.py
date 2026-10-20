"""Fictional company examples added only to the isolated local demonstration."""

import hashlib

from app.models.companies import CompanyFact, CompanyRecord
from app.models.provenance import FactSource
from app.services.seed_data import SEED_DATE, build_demo_seed
from app.services.workspace import serialize


def local_seed():
    seed = build_demo_seed()
    seed["companies"] = []
    for i, developer in enumerate(seed["developers"][:2], 1):
        source = FactSource(
            publisher="DEMO — вымышленный источник компании",
            url=f"https://demo.invalid/companies/{i}",
            retrieved_at=SEED_DATE,
            response_sha256=hashlib.sha256(f"fictional-company-{i}".encode()).hexdigest(),
        )
        company = CompanyRecord(
            id=f"bin-{developer['bin']}",
            bin=developer["bin"],
            name=developer["name"],
            updated_at=SEED_DATE,
            facts=[
                CompanyFact(field="name", value=developer["name"], source=source),
                CompanyFact(field="bin", value=developer["bin"], source=source),
            ],
        )
        seed["companies"].append(serialize(company))
    # Add two explicit fictional shared contacts for the advertising-trace screen.
    for ad in seed["advertisements"][-2:]:
        ad["text"] += " DEMO — учебный контакт: +7 (000) 000-00-01."
    return seed
