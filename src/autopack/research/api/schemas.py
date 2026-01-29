from pydantic import BaseModel, ConfigDict, Field


class ResearchSession(BaseModel):
    """Research session response model."""

    session_id: str
    status: str
    created_at: str
    topic: str
    description: str


class CreateResearchSession(BaseModel):
    """Request model for creating a research session."""

    topic: str = Field(..., min_length=1, max_length=200, description="Research topic")
    description: str = Field(..., min_length=1, max_length=2000, description="Research description")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"topic": "AI Research", "description": "Exploring new AI techniques"}
        }
    )


class UpdateResearchSession(BaseModel):
    """Request model for updating a research session."""

    status: str = Field(..., min_length=1, description="New session status")

    model_config = ConfigDict(json_schema_extra={"example": {"status": "completed"}})
