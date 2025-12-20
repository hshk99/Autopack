from pydantic import BaseModel

class ResearchSession(BaseModel):
    session_id: str
    status: str
    created_at: str
    topic: str
    description: str

class CreateResearchSession(BaseModel):
    topic: str
    description: str

    class Config:
        schema_extra = {
            "example": {
                "topic": "AI Research",
                "description": "Exploring new AI techniques"
            }
        }

class UpdateResearchSession(BaseModel):
    status: str

    class Config:
        schema_extra = {
            "example": {
                "status": "completed"
            }
        }

