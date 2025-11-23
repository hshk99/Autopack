FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# Per v7 architect recommendation: git needed for governed apply path
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "src.autopack.main:app", "--host", "0.0.0.0", "--port", "8000"]
