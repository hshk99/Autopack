"""Main application entry point for FastAPI"""

from fastapi import FastAPI
from .api.auth import router as auth_router
from .api.search import include_router as include_search_router
from .database import Base, engine

app = FastAPI(
    title="Autopack Backend",
    description="Backend services for Autopack",
    version="0.1.0"
)

@app.on_event("startup")
def on_startup():
    # Ensure database tables exist
    Base.metadata.create_all(bind=engine)

# Include routers
app.include_router(auth_router)
include_search_router(app)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
