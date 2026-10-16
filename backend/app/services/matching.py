"""Read-only name/alias candidates. Never relinks advertisements or confirms findings."""

import re
import unicodedata

from app.core.errors import AppError
from app.models.analysis import Extraction
from app.models.entities import Advertisement, Complex
from app.services.workspace import WorkspaceService


def normalized_name(value: str) -> str:
    words = re.findall(
        r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    )
    # Discard labels, never infer a new project from common branding words alone.
    while words and words[0] in {"demo", "жк", "zhk"}:
        words.pop(0)
    return " ".join(words)


def candidate_reason(mention: str, complex_: Complex) -> tuple[int, str, str] | None:
    normalized = normalized_name(mention)
    if not normalized:
        return None
    for index, name in enumerate([complex_.name, *complex_.aliases]):
        known = normalized_name(name)
        if normalized == known:
            return (0, "name", name) if index == 0 else (1, "alias", name)
    tokens = set(normalized.split())
    for name in [complex_.name, *complex_.aliases]:
        known_tokens = set(normalized_name(name).split())
        # At least two shared words: a single 'квартал' must not propose half the registry.
        if len(tokens & known_tokens) >= 2 and (tokens <= known_tokens or known_tokens <= tokens):
            return 2, "partial_name", name
    return None


def match_candidates(workspace: WorkspaceService, ad_id: str, run_id: str) -> dict:
    ad = Advertisement.model_validate(workspace.require_record("advertisements", ad_id))
    run = workspace.require_record("analysisRuns", run_id)
    if run["advertisementId"] != ad_id:
        raise AppError(422, "ANALYSIS_MISMATCH", "Analysis belongs to another advertisement")
    if run["status"] != "succeeded":
        raise AppError(409, "ANALYSIS_INCOMPLETE", "Choose a completed analysis")
    extraction = Extraction.model_validate(run["extraction"])
    filters = [("demo", "==", True)] if workspace.demo_only else []
    rows = workspace.store.list("complexes", filters=filters, limit=500)
    complexes = [Complex.model_validate(row) for row in rows]
    groups = []
    for mention in dict.fromkeys(extraction.mentioned_complexes):
        matches = []
        for complex_ in complexes:
            reason = candidate_reason(mention, complex_)
            if reason:
                rank, kind, matched_name = reason
                matches.append(
                    (
                        rank,
                        {
                            "complexId": complex_.id,
                            "name": complex_.name,
                            "city": complex_.city,
                            "matchedBy": kind,
                            "matchedName": matched_name,
                            "demo": complex_.demo,
                        },
                    )
                )
        matches.sort(key=lambda item: (item[0], item[1]["name"].casefold(), item[1]["complexId"]))
        groups.append(
            {
                "mention": mention,
                "ambiguous": len(matches) > 1,
                "candidateCount": len(matches),
                "candidatesLimited": len(matches) > 10,
                "candidates": [item[1] for item in matches[:10]],
            }
        )
    return {
        "runId": run_id,
        "advertisementId": ad_id,
        "currentComplexId": ad.complex_id,
        "catalogLimited": len(rows) == 500,
        "groups": groups,
    }
