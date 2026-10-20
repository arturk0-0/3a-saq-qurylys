"""Opt-in QA composition with B's actual backend, never a production import.

Only external providers/Auth/store/files are test adapters. Materials API, jobs,
dedup, review transaction, factors and PDF all run the real backend code.
"""

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager, suppress

import httpx
import local_api
from app.models.auth import Principal
from app.services.gemini import GeminiClient
from app.services.material_analysis import MaterialProcessor
from fastapi import Request
from fastapi.responses import JSONResponse

app = local_api.app
counts = {}


def counted_response(request):
    payload = json.loads(request.content)
    source = json.loads(payload["contents"][0]["parts"][0]["text"])["sourceText"]
    digest = hashlib.sha256(source.encode()).hexdigest()
    counts[digest] = counts.get(digest, 0) + 1
    return local_api.model_response(request)


client = GeminiClient(local_api.settings, httpx.MockTransport(counted_response))
app.state.material_client = client
app.state.material_files = local_api.files
processor = MaterialProcessor(
    local_api.workspace, client, local_api.files, local_api.settings
)
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def qa_lifespan(application):
    async def worker():
        while True:
            await asyncio.to_thread(
                processor.process,
                Principal(uid="qa-material-worker", role="analyst"),
                3,
            )
            await asyncio.sleep(0.3)

    async with original_lifespan(application):
        task = asyncio.create_task(worker())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app.router.lifespan_context = qa_lifespan


@app.get("/api/qa-materials/provider-counts")
def provider_counts(request: Request):
    if request.headers.get("authorization") != "Bearer qa-local-analyst":
        return JSONResponse({"code": "INVALID_TOKEN"}, 401)
    return {"counts": dict(counts), "adapter": "MockTransport; no live AI"}
