# Multi-stage build for Autopack Framework
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 autopack && \
    mkdir -p /app && \
    chown -R autopack:autopack /app

WORKDIR /app

# Copy requirements first for better caching
COPY --chown=autopack:autopack requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=autopack:autopack . .

# Switch to non-root user
USER autopack

# Create necessary directories
RUN mkdir -p /app/.autonomous_runs /app/logs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Default command - run with uvicorn
CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Development stage with additional tools
FROM base as development
USER root
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov black ruff mypy
USER autopack
