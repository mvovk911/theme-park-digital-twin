from pydantic import BaseModel, ConfigDict, Field


class WorkflowError(ValueError):
    def __init__(self, code, message, status=409, context=None):
        self.code, self.message, self.status = code, message, status
        self.context = context
        super().__init__(message)


class CreateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    branch_id: str = Field(min_length=1, max_length=48, pattern=r"^[a-z][a-z0-9_-]*$")
    action_index: int = Field(ge=0, le=5, strict=True)
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    ttl_seconds: int = Field(default=120, ge=30, le=300, strict=True)


class ExecuteProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class CreateIncident(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    ttl_seconds: int = Field(default=120, ge=30, le=300, strict=True)
    rationale_bundle_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
