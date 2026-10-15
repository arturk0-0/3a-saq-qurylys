from pydantic import AwareDatetime, Field

from app.models.common import DomainModel, Identifier


class AuditEvent(DomainModel):
    id: Identifier
    entity_type: str
    entity_id: Identifier
    complex_id: Identifier | None = None
    action: str
    actor_uid: str
    created_at: AwareDatetime
    demo: bool
    details: dict = Field(default_factory=dict)
