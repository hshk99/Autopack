"""
Main FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .core.config import settings
from .api.auth import router as auth_router
from .api.middleware import log_requests_middleware, error_handling_middleware
from .models.user import Base
from .api.dependencies import engine


# Create database tables
Base.metadata.create_all(bind=engine)


# Initialize FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Autonomous AI Code Generation Framework API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add custom middleware
app.middleware("http")(log_requests_middleware)
app.middleware("http")(error_handling_middleware)


# Include routers
app.include_router(auth_router, prefix="/api")


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "message": "Autopack API",
        "version": "0.1.0",
        "docs": "/api/docs"
    }


@app.get("/api/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
