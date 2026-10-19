"""Bounded, synthetic planning inputs. A plan never implies command authorization."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Scenario = Literal["normal", "ride_closure", "show_surge", "heatwave", "power_fault", "water_leak", "food_rush"]
Action = Literal["dispatch_maintenance", "reroute_guests", "add_staff", "shed_load", "repair_leak", "replenish_stock"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)


class ScheduledAction(StrictModel):
    action: Action
    asset_id: str = Field(min_length=1, max_length=64)
    at_minute: int = Field(default=0, ge=0, le=120, strict=True)


class Candidate(StrictModel):
    id: str = Field(min_length=1, max_length=48, pattern=r"^[a-z][a-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=100)
    actions: list[ScheduledAction] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def unique_actions(self):
        keys = [(a.action, a.asset_id if a.action == "add_staff" else "park") for a in self.actions]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate action effects in one candidate are unsupported")
        return self


class Assumptions(StrictModel):
    arrival_multiplier: float = Field(default=1.0, ge=0.25, le=3)
    demand_uncertainty_pct: float = Field(default=20, ge=0, le=50)
    available_qualified_staff: int = Field(default=4, ge=0, le=12, strict=True)
    routing_compliance_pct: float = Field(default=25, ge=0, le=100)


class PlanningRequest(StrictModel):
    scenario: Scenario
    horizon_minutes: int = Field(default=60, ge=15, le=120, strict=True)
    expected_state_revision: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    candidates: list[Candidate] | None = Field(default=None, max_length=6)
    assumptions: Assumptions = Field(default_factory=Assumptions)

    @model_validator(mode="after")
    def valid_horizon(self):
        if self.horizon_minutes % 5:
            raise ValueError("horizon_minutes must be a multiple of five")
        ids = [c.id for c in self.candidates or []]
        if len(ids) != len(set(ids)) or "baseline" in ids:
            raise ValueError("Candidate ids must be unique and cannot use reserved id baseline")
        if any(a.at_minute % 5 or a.at_minute >= self.horizon_minutes
               for c in self.candidates or [] for a in c.actions):
            raise ValueError("Actions must start on five-minute boundaries before the horizon")
        return self
