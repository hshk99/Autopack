"""
FileOrganizer Backend - FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.middleware import error_handler_middleware
from app.core.logging import setup_logging
from app.routers import health, documents, packs, classification, export

# Setup logging
logger = setup_logging()

app = FastAPI(
    title="FileOrganizer API",
    description="Document processing and organization backend",
    version="1.0.0"
)

# CORS middleware for Electron frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Electron renderer
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Error handling middleware
app.middleware("http")(error_handler_middleware)

# Routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
app.include_router(packs.router, prefix="/api/v1", tags=["packs"])
app.include_router(classification.router, prefix="/api/v1", tags=["classification"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])

@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup"""
    from app.db.session import init_db
    init_db()
    print("[OK] FileOrganizer backend started successfully")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
