from fastapi import APIRouter, HTTPException
from typing import List
from src.autopack.research.api.schemas import ResearchSession, CreateResearchSession

research_router = APIRouter()

# Mock database
research_sessions = []

@research_router.get("/sessions", response_model=List[ResearchSession])
async def get_research_sessions():
    """
    Retrieve all research sessions.
    """
    return research_sessions

@research_router.post("/sessions", response_model=ResearchSession, status_code=201)
async def create_research_session(session: CreateResearchSession):
    """
    Create a new research session.
    """
    new_session = ResearchSession(session_id="session_" + str(len(research_sessions) + 1),
                                  status="active",
                                  created_at="2025-12-20T12:00:00Z",
                                  topic=session.topic,
                                  description=session.description)
    research_sessions.append(new_session)
    return new_session

@research_router.get("/sessions/{session_id}", response_model=ResearchSession)
async def get_research_session(session_id: str):
    """
    Retrieve a specific research session by ID.
    """
    for session in research_sessions:
        if session.session_id == session_id:
            return session
    raise HTTPException(status_code=404, detail="Session not found")

