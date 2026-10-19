"""Bounded read-only authored-design queries, with no actuation fields."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Variant = Literal['baseline', 'dining_connection']
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')]
MAX_REQUEST_BYTES = 16 * 1024


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False, validate_default=True)
    variant: Variant = 'baseline'
    origin: Identifier
    destination: Identifier
    blocked_edges: list[Identifier] = Field(default_factory=list, max_length=32)
    accessible_only: bool = False
    walking_speed_mps: float = Field(default=1.2, ge=.3, le=2.5)

    @model_validator(mode='after')
    def unique_closures(self):
        if len(set(self.blocked_edges)) != len(self.blocked_edges):
            raise ValueError('Duplicate blocked edge IDs are not accepted')
        return self
