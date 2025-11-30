# Multi-stage build for Python backend
FROM python:3.11-slim as backend-builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final backend stage
FROM python:3.11-slim as backend

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=backend-builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY alembic.ini .
COPY alembic/ ./alembic/

# Create non-root user
RUN useradd -m -u 1000 autopack && chown -R autopack:autopack /app
USER autopack

EXPOSE 8000

# Run uvicorn server
CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
