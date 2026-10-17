"""Server-generated request IDs, propagated into synchronous worker threads."""

from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("saq_request_id", default="outside-request")
