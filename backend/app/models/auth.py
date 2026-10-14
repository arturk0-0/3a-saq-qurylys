from typing import Literal

from pydantic import Field

from app.models.common import DomainModel


class Principal(DomainModel):
    uid: str = Field(min_length=1, max_length=128)
    role: Literal["analyst", "admin"]
    email: str | None = None
    display_name: str | None = None
