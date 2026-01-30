# Container Best Practices

This guide covers Docker and container best practices for building secure, optimized, and efficient container images for production deployments.

## Table of Contents

- [Security Best Practices](#security-best-practices)
- [Image Optimization](#image-optimization)
- [Multi-Stage Builds](#multi-stage-builds)
- [Build Efficiency](#build-efficiency)
- [Runtime Configuration](#runtime-configuration)
- [Health Checks and Lifecycle](#health-checks-and-lifecycle)
- [Container Scanning and Validation](#container-scanning-and-validation)
- [Common Patterns](#common-patterns)
- [Troubleshooting](#troubleshooting)

---

## Security Best Practices

### 1. Use Minimal Base Images

Always prefer minimal base images to reduce attack surface and image size.

**Recommended base images:**

- `python:3.11-slim` or `python:3.11-alpine` for Python applications
- `node:18-alpine` for Node.js applications
- `alpine:latest` for lightweight utilities
- `distroless/python3.11` for minimal Python footprint
- `ubuntu:22.04` or `debian:bookworm-slim` for standard Linux

**Avoid:**

- Full OS images (e.g., `ubuntu:latest`, `centos:latest`) when slim/alpine alternatives exist
- Outdated base image tags (always specify versions, not `latest`)

**Example:**

```dockerfile
# Bad
FROM ubuntu:latest
RUN apt-get update && apt-get install python3

# Good
FROM python:3.11-alpine
# Already includes Python 3.11
```

### 2. Run as Non-Root User

Containers should never run as root by default. Create dedicated users for application processes.

**Implementation:**

```dockerfile
# Create a non-root user
RUN addgroup --system appgroup && \
    adduser --system --group appuser

# Switch to non-root user
USER appuser

# Application runs with appuser privileges
CMD ["python", "app.py"]
```

**Benefits:**

- Limits damage from container escape vulnerabilities
- Enforces least privilege principle
- Aligns with Kubernetes Pod Security Standards

### 3. Keep Base Images Updated

Regularly update base images to patch security vulnerabilities.

**Best practices:**

- Periodically rebuild images with updated base layers
- Use specific version tags: `python:3.11.5-alpine` (not `3.11-alpine`)
- Set up automated rebuild pipelines
- Monitor security advisories for base images

**Automatic rebuild trigger:**

```yaml
# CI/CD pipeline example
- name: Rebuild if base image updated
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday
  steps:
    - docker build --no-cache -t app:latest .
    - docker push app:latest
```

### 4. Minimize Installed Packages

Only install packages required for production runtime.

**Good practices:**

```dockerfile
# Install only necessary packages
RUN apk add --no-cache \
    curl \
    postgresql-client

# Don't install:
# - Build tools (gcc, make, git)
# - Development libraries
# - Documentation packages
# - Package manager caches
```

**Remove package manager cache:**

```dockerfile
RUN apt-get update && \
    apt-get install -y package1 package2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
```

### 5. Don't Store Secrets in Images

Secrets should never be baked into container images.

**Wrong approach:**

```dockerfile
# ❌ DON'T DO THIS
ENV API_KEY=secret123
COPY .env /app/.env
```

**Correct approach:**

```dockerfile
# ✓ Use runtime injection
# Secrets provided via:
# - Environment variables (docker run -e or Kubernetes secrets)
# - Volume mounts (/run/secrets)
# - Secret management services (HashiCorp Vault, AWS Secrets Manager)
```

**Kubernetes example:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
type: Opaque
stringData:
  api_key: secret123

---
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    image: app:1.0
    env:
    - name: API_KEY
      valueFrom:
        secretKeyRef:
          name: app-secrets
          key: api_key
```

### 6. Use .dockerignore

Exclude unnecessary files from the build context to speed up builds and reduce image size.

**.dockerignore example:**

```
# Version control
.git
.gitignore
.gitattributes

# CI/CD
.github
.gitlab-ci.yml
.circleci

# Development
.vscode
.idea
*.swp
*.swo

# Python
__pycache__
*.pyc
*.pyo
.pytest_cache
.coverage
venv/
.env

# Build artifacts
dist/
build/
*.egg-info

# Documentation
README.md
docs/

# Test files
tests/
test_*.py
```

### 7. Scan Images for Vulnerabilities

Use vulnerability scanning tools to identify and remediate security issues.

**Popular scanning tools:**

- **Trivy**: Fast, comprehensive vulnerability scanner
  ```bash
  trivy image app:1.0
  trivy image --severity HIGH,CRITICAL app:1.0
  ```

- **Snyk**: Developer-focused security scanning
  ```bash
  snyk container test app:1.0
  ```

- **Docker Scout**: Docker's built-in scanner
  ```bash
  docker scout cves app:1.0
  ```

**CI/CD integration:**

```yaml
- name: Scan image for vulnerabilities
  run: |
    trivy image --exit-code 1 --severity HIGH,CRITICAL app:1.0
```

---

## Image Optimization

### 1. Use Multi-Stage Builds

Multi-stage builds drastically reduce final image size by separating build dependencies from runtime artifacts.

**Single-stage (bloated):**

```dockerfile
FROM python:3.11
WORKDIR /app

# Install build tools
RUN apt-get update && \
    apt-get install -y build-essential git

# Copy source
COPY . .

# Build and install
RUN pip install .

# Run application
CMD ["python", "-m", "app"]

# Final image includes:
# - Build tools (not needed at runtime)
# - Compiler, git, development libraries
# - Size: ~1.5GB
```

**Multi-stage (optimized):**

```dockerfile
# Stage 1: Builder
FROM python:3.11 AS builder
WORKDIR /build

RUN apt-get update && \
    apt-get install -y build-essential

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim
WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY src/ .

ENV PATH=/root/.local/bin:$PATH

CMD ["python", "app.py"]

# Final image includes only runtime dependencies
# - Size: ~150MB (90% reduction)
```

### 2. Minimize Layer Count

Each Dockerfile instruction creates a layer. Combine commands to reduce layers.

**Before (8 layers):**

```dockerfile
FROM alpine:latest
RUN apk add --no-cache python3
RUN apk add --no-cache py3-pip
RUN mkdir -p /app
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

**After (4 layers):**

```dockerfile
FROM alpine:latest
RUN apk add --no-cache python3 py3-pip
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

### 3. Optimize Layer Ordering

Place frequently-changing instructions late in the Dockerfile to maximize cache reuse.

**Inefficient (cache misses):**

```dockerfile
FROM python:3.11-slim
COPY . /app                    # Changes often
WORKDIR /app
COPY requirements.txt .        # Changes less often
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

**Efficient (cache hits):**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .        # Changes less often
RUN pip install -r requirements.txt
COPY . /app                    # Changes often (cache reused above)
CMD ["python", "app.py"]
```

### 4. Remove Build Artifacts

Clean up unnecessary files after building to reduce image size.

```dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apt/*

COPY src/ .
RUN python -m py_compile src/

CMD ["python", "app.py"]
```

### 5. Compress Sensitive Files

Use compression for configuration files if needed.

```dockerfile
COPY config.json.gz /app/
RUN gunzip /app/config.json.gz
```

---

## Multi-Stage Builds

### Development vs. Production Images

Create separate images optimized for each environment.

**Development image (includes debugging tools):**

```dockerfile
FROM python:3.11 AS development
WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    vim \
    curl \
    ipython3

COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

COPY . .
CMD ["python", "-m", "debugpy.adapter"]
```

**Production image (minimal, hardened):**

```dockerfile
FROM python:3.11-slim AS production
WORKDIR /app

RUN addgroup --system appgroup && \
    adduser --system --group appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

COPY --chown=appuser:appgroup src/ .

USER appuser
CMD ["python", "app.py"]
```

### Build Artifact Handling

Use multi-stage builds to manage compilation artifacts.

**Example: Go application with compile optimization:**

```dockerfile
# Stage 1: Build
FROM golang:1.21 AS builder
WORKDIR /build
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o app .

# Stage 2: Runtime
FROM alpine:latest
RUN apk add --no-cache ca-certificates
COPY --from=builder /build/app /usr/local/bin/

ENTRYPOINT ["app"]
```

---

## Build Efficiency

### 1. Layer Caching Strategy

Leverage Docker's layer caching by arranging instructions strategically.

**Cache key principles:**

- Each instruction creates a new layer
- Layers are cached based on the Dockerfile instruction and files it references
- If the instruction or files change, the layer and all subsequent layers are rebuilt
- A cache miss causes all downstream layers to rebuild

**Optimal ordering:**

```dockerfile
# 1. Least frequently changed (base image)
FROM python:3.11-slim

# 2. System dependencies (rarely change)
RUN apt-get update && \
    apt-get install -y postgresql-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. Python dependencies (change when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Application code (changes frequently)
COPY src/ /app/src

# 5. Configuration (may change per deployment)
COPY config.yaml /app/

# 6. Entry point (rarely changes)
CMD ["python", "-m", "app"]
```

### 2. Parallel Builds

Use BuildKit for faster builds with better caching.

**Enable BuildKit:**

```bash
export DOCKER_BUILDKIT=1
docker build -t app:1.0 .
```

**Docker Compose with BuildKit:**

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    image: app:1.0
```

### 3. BuildKit Advanced Features

```dockerfile
# Syntax directive for BuildKit features
# syntax=docker/dockerfile:1

# BuildKit-specific cache mounts for package managers
FROM python:3.11-slim
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Conditional build stages
FROM python:3.11-slim AS stage1
# ...build logic...

FROM stage1 AS stage2
# ...more logic...
```

---

## Runtime Configuration

### 1. Health Checks

Configure health checks to monitor container health.

**Basic health check:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .

# Health check definition
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "app.py"]
```

**Advanced health check with custom script:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .

# Create health check script
COPY healthcheck.py /app/
RUN chmod +x /app/healthcheck.py

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python /app/healthcheck.py

CMD ["python", "app.py"]
```

**Health check script example:**

```python
#!/usr/bin/env python3
import requests
import sys

try:
    response = requests.get('http://localhost:8000/health', timeout=5)
    if response.status_code == 200:
        sys.exit(0)  # Healthy
    else:
        sys.exit(1)  # Unhealthy
except Exception as e:
    print(f"Health check failed: {e}")
    sys.exit(1)  # Unhealthy
```

### 2. Signal Handling (SIGTERM)

Properly handle SIGTERM for graceful shutdowns.

**Python example (FastAPI):**

```python
import signal
import asyncio
from fastapi import FastAPI
import uvicorn

app = FastAPI()
server = None

@app.get("/health")
async def health():
    return {"status": "healthy"}

def signal_handler(sig, frame):
    print("Received SIGTERM, shutting down gracefully...")
    asyncio.current_task().cancel()
    raise KeyboardInterrupt()

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
```

**Dockerfile for graceful shutdown:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .

# Set stop signal to SIGTERM (default for containers)
STOPSIGNAL SIGTERM

# Timeout for graceful shutdown (default 10s)
CMD ["python", "app.py"]
```

### 3. User Permissions

Run containers with restricted permissions.

```dockerfile
# Create dedicated user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Set ownership and permissions
COPY --chown=appuser:appgroup src/ /app/src
RUN chmod 755 /app/src

USER appuser
CMD ["python", "app.py"]
```

**Kubernetes with Pod Security Standards:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: app
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
  containers:
  - name: app
    image: app:1.0
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop:
        - ALL
      readOnlyRootFilesystem: true
```

---

## Health Checks and Lifecycle

### 1. Container Lifecycle Events

Understand container startup, running, and shutdown phases.

**Startup phase:**

- Container starts with `docker run` or orchestrator
- Executes `CMD` or `ENTRYPOINT`
- HEALTHCHECK starts after START_PERIOD
- Application should be ready to accept traffic

**Running phase:**

- Application processes requests
- Health checks run at regular intervals
- Logs are collected from stdout/stderr

**Shutdown phase:**

- Orchestrator sends SIGTERM signal
- Application has grace period (typically 30s) to shut down
- If not stopped, orchestrator sends SIGKILL (force terminate)

**Dockerfile configuration:**

```dockerfile
FROM python:3.11-slim

# Grace period for shutdown (seconds)
ENV GRACEFUL_SHUTDOWN_TIMEOUT=30

# Health check timing
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python /app/healthcheck.py

# Signals
STOPSIGNAL SIGTERM

# Process
CMD ["python", "app.py"]
```

### 2. Logging Best Practices

Ensure proper log output for container monitoring.

```dockerfile
FROM python:3.11-slim

# Set Python to output directly to stdout (no buffering)
ENV PYTHONUNBUFFERED=1

# Log to stdout/stderr (not files)
CMD ["python", "-u", "app.py"]
```

**Python logging configuration:**

```python
import logging
import sys

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
logger.info("Application started")
```

---

## Container Scanning and Validation

### 1. Vulnerability Scanning

Integrate vulnerability scanning into your CI/CD pipeline.

**Trivy scanning:**

```bash
# Scan image
trivy image app:1.0

# Scan with severity filter
trivy image --severity HIGH,CRITICAL app:1.0

# Generate SBOM (Software Bill of Materials)
trivy image --format cyclonedx --output sbom.json app:1.0

# Scan with custom policy
trivy image --skip-policy app:1.0
```

**CI/CD integration (GitHub Actions):**

```yaml
name: Container Scan
on: [push]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build image
        run: docker build -t app:${{ github.sha }} .

      - name: Scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: app:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload scan results
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'
```

### 2. Image Validation

Validate image content before deployment.

**Size checks:**

```bash
# Check image size
docker image ls app:1.0

# Alert if exceeds threshold
SIZE=$(docker inspect --format='{{.Size}}' app:1.0)
MAX_SIZE=$((500 * 1024 * 1024))  # 500MB
if [ $SIZE -gt $MAX_SIZE ]; then
  echo "Image exceeds size limit!"
  exit 1
fi
```

**Layer analysis:**

```bash
# View image layers
docker image inspect app:1.0 --format='{{.RootFS.Layers}}'

# Check for unnecessary packages
docker run --rm app:1.0 pip list
docker run --rm app:1.0 apt list --installed
```

### 3. Runtime Security

Validate container behavior at runtime.

```bash
# Run container with security options
docker run --rm \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --read-only \
  --security-opt=no-new-privileges:true \
  app:1.0

# Audit syscalls (requires AppArmor/SELinux)
docker run --security-opt apparmor=docker-default app:1.0
```

---

## Common Patterns

### 1. Development Environment

Full-featured development image with debugging tools.

```dockerfile
FROM python:3.11
WORKDIR /app

# Install dev tools
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    vim \
    curl \
    postgresql-client \
    && apt-get clean

# Install Python dev dependencies
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

# Mount source code as volume
VOLUME ["/app"]

# Enable debugging
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "debugpy.adapter"]
```

**Run command:**

```bash
docker run -it --rm \
  -v $(pwd):/app \
  -p 5678:5678 \
  app:dev
```

### 2. Production Image

Minimal, hardened production image.

```dockerfile
FROM python:3.11-slim AS runtime
WORKDIR /app

# Security: non-root user
RUN addgroup --system appgroup && \
    adduser --system --group appuser

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# Application
COPY --chown=appuser:appgroup src/ .

# Security
USER appuser
STOPSIGNAL SIGTERM

# Health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "app"]
```

### 3. CI/CD Artifact Pipeline

Build, test, and deploy with multi-stage builds.

```dockerfile
# Stage 1: Builder
FROM golang:1.21 AS builder
WORKDIR /build
COPY . .
RUN go test ./...
RUN CGO_ENABLED=0 go build -o app .

# Stage 2: Tester
FROM golang:1.21 AS tester
WORKDIR /build
COPY . .
RUN go test -v ./...

# Stage 3: Runtime
FROM alpine:latest AS runtime
RUN apk add --no-cache ca-certificates
COPY --from=builder /build/app /usr/local/bin/
ENTRYPOINT ["app"]
```

---

## Troubleshooting

### Issue: Image Size Too Large

**Diagnosis:**

```bash
docker history app:1.0
docker image inspect app:1.0 --format='{{.Size}}'
```

**Solutions:**

1. Use slim/alpine base images
2. Remove build dependencies
3. Combine RUN commands
4. Use multi-stage builds
5. Clean package manager caches

### Issue: Slow Builds

**Diagnosis:**

```bash
# Disable BuildKit to see timing per layer
DOCKER_BUILDKIT=0 docker build -t app:1.0 . --progress=plain
```

**Solutions:**

1. Enable BuildKit (`DOCKER_BUILDKIT=1`)
2. Reorder Dockerfile instructions for cache hits
3. Use .dockerignore to reduce context
4. Consider split builds for different parts

### Issue: Container Won't Start

**Debugging:**

```bash
# View logs
docker run --rm app:1.0
docker logs <container-id>

# Run with entrypoint override
docker run --rm --entrypoint /bin/sh app:1.0

# Check permissions
docker run --rm app:1.0 id
docker run --rm app:1.0 ls -la /app
```

### Issue: Health Check Failing

**Diagnosis:**

```bash
# Check health status
docker inspect <container-id> | grep -A 10 Health

# Run health check manually
docker exec <container-id> curl http://localhost:8000/health
```

**Solutions:**

1. Verify health check path/command is correct
2. Increase start period if app needs time to initialize
3. Check network connectivity in container
4. Review application logs for errors

---

## References

- [Docker Documentation](https://docs.docker.com/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Trivy Security Scanner](https://github.com/aquasecurity/trivy)
- [OWASP Container Security](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
