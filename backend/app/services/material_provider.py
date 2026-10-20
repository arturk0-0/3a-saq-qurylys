"""One paid-call gate shared by automatic and legacy analysis entry points."""

from datetime import timedelta
from uuid import uuid4

from app.core.errors import AppError, Conflict
from app.models.analysis import Extraction
from app.models.common import utc_now
from app.services.gemini import PROMPT_VERSION
from app.services.material_projection import digest


def input_call_key(scope, text, image_sha, settings):
    return digest(f"{scope}:{digest(text)}:{image_sha}:{settings.gemini_model}:{PROMPT_VERSION}")


def cached_extract(workspace, settings, client, text, image, user, scope):
    import hashlib

    image_sha = hashlib.sha256(image[0]).hexdigest() if image else ""
    key = input_call_key(scope, text, image_sha, settings)
    now, token = utc_now(), str(uuid4())
    quota_ids = [f"global-{now:%Y%m%d}", f"user-{digest(user.uid)}-{now:%Y%m%d}"]

    def reserve(tx):
        existing = tx.get("materialProviderCalls", key)
        counters = [tx.get("usageLimits", k) or {"id": k, "count": 0} for k in quota_ids]
        if existing:
            if existing["status"] == "ready":
                return existing
            if existing["status"] == "failed":
                raise AppError(409, "AI_RETRY_REQUIRED", "Use explicit retry for failed input")
            if (
                existing["status"] == "running"
                and existing.get("leaseUntil", "") <= now.isoformat()
            ):
                raise AppError(409, "AI_OUTCOME_UNKNOWN", "The previous paid outcome is unknown")
            if existing["status"] != "retry_authorized":
                raise AppError(409, "AI_BUSY", "An analysis of this input is already in progress")
        if any(
            c["count"] >= cap
            for c, cap in zip(
                counters,
                [settings.ai_daily_global_limit, settings.ai_daily_user_limit],
                strict=True,
            )
        ):
            raise AppError(429, "AI_DAILY_LIMIT", "Daily analysis limit reached")
        run = {
            "id": key,
            "status": "running",
            "attemptToken": token,
            "createdAt": now.isoformat(),
            "leaseUntil": (now + timedelta(minutes=10)).isoformat(),
            "model": settings.gemini_model,
            "promptVersion": PROMPT_VERSION,
        }
        tx.create("materialProviderAttempts", token, {**run, "id": token, "callId": key})
        tx.set("materialProviderCalls", key, run)
        for c in counters:
            tx.set("usageLimits", c["id"], {**c, "count": c["count"] + 1})
        return run

    client.check_config()
    call = workspace.store.atomic(reserve)
    if call["status"] == "ready":
        return Extraction.model_validate(call["extraction"])
    try:
        result = Extraction.model_validate(client.extract(text, image))
        if not image and any(h.quote not in text for h in result.hypotheses):
            raise AppError(502, "AI_INVALID_RESPONSE", "Unanchored source quote")

        def complete(tx):
            current = tx.get("materialProviderCalls", key)
            attempt = tx.get("materialProviderAttempts", token)
            if current["status"] != "running" or current["attemptToken"] != token:
                raise Conflict("A newer paid analysis replaced this result")
            tx.set(
                "materialProviderAttempts",
                token,
                {**attempt, "status": "ready", "completedAt": utc_now().isoformat()},
            )
            tx.set(
                "materialProviderCalls",
                key,
                {
                    **current,
                    "status": "ready",
                    "completedAt": utc_now().isoformat(),
                    "extraction": result.model_dump(mode="json", by_alias=True),
                },
            )

        workspace.store.atomic(complete)
        return result
    except Exception as error:
        code = error.code if isinstance(error, AppError) else "ANALYSIS_FAILED"

        def fail(tx):
            current = tx.get("materialProviderCalls", key)
            attempt = tx.get("materialProviderAttempts", token)
            if current and current["status"] == "running" and current["attemptToken"] == token:
                tx.set(
                    "materialProviderAttempts",
                    token,
                    {
                        **attempt,
                        "status": "failed",
                        "errorCode": code,
                        "completedAt": utc_now().isoformat(),
                    },
                )
                tx.set(
                    "materialProviderCalls", key, {**current, "status": "failed", "errorCode": code}
                )

        workspace.store.atomic(fail)
        raise
