"""Main application entry point for FastAPI"""

from fastapi import FastAPI
from .api.search import include_router as include_search_router

app = FastAPI(
    title="Autopack Backend",
    description="Backend services for Autopack",
    version="0.1.0"
)

# Include the search router
include_search_router(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
