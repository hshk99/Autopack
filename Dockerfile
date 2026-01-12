# Dockerfile for Autopack backend
#
# Base Image Policy (P3.1: Digest Pinning):
# - Images are pinned to SHA256 digests for supply-chain security
# - Digest pinning ensures reproducible builds and protects against tag hijacking
# - Update procedure: Check Docker Hub for new digests, update here, test, commit
#
# Current pins (last updated: 2026-01-10):
# - python:3.11-slim-bookworm@sha256:55a4707a91d43b6397215a57b818d2822e66c27fd973bb82eb71b7512c15a4da
#
# Frontend Note:
# - The canonical frontend is built via Dockerfile.frontend (root Vite app)
# - docker-compose.yml uses Dockerfile.frontend for the frontend service
# - See docs/IMPROVEMENTS_GAP_ANALYSIS.md section 0.2 for the canonical direction decision

# Use an official Python runtime as a parent image
# P3.1: Pinned to digest for reproducible builds and supply-chain security
FROM python:3.14-slim-bookworm@sha256:e8a1ad81a9fef9dc56372fb49b50818cac71f5fae238b21d7738d73ccae8f803 as backend

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
