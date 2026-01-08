# Dockerfile for Autopack backend
#
# Base Image Policy:
# - Using version tags (e.g., python:3.11-slim) instead of SHA digests
# - Tradeoff: Security (immutable digests) vs Maintainability (auto-patches)
# - Rationale: Dependabot monitors Docker images; digest pinning deferred to P5 hardening
# - For production with strict supply-chain requirements, pin to digests:
#   FROM python:3.11-slim@sha256:<digest>
#
# Frontend Note:
# - The canonical frontend is built via Dockerfile.frontend (root Vite app)
# - docker-compose.yml uses Dockerfile.frontend for the frontend service
# - See docs/IMPROVEMENTS_GAP_ANALYSIS.md section 0.2 for the canonical direction decision

# Use an official Python runtime as a parent image
FROM python:3.11-slim as backend

# Set the working directory in the container
WORKDIR /app

# Runtime safety defaults
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Copy the current directory contents into the container at /app
COPY ./src /app/src
COPY ./requirements.txt /app

# Copy config files required at runtime (models.yaml, pricing.yaml, etc.)
# These are needed for deterministic model routing and policy enforcement
COPY ./config /app/config

# Install any needed packages specified in requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Run as non-root (defense-in-depth)
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run uvicorn server
CMD ["uvicorn", "autopack.main:app", "--host", "0.0.0.0", "--port", "8000"]
