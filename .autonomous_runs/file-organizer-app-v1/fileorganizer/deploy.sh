#!/bin/bash
# FileOrganizer Deployment Helper Script
# Usage: ./deploy.sh [command] [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default values
ENV_FILE=".env"
COMPOSE_FILE="docker-compose.yml"

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  FileOrganizer Deployment${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    print_success "Docker is installed"
    
    if ! command -v docker compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    print_success "Docker Compose is installed"
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
    print_success "Docker daemon is running"
}

# Create .env file if it doesn't exist
setup_env() {
    if [ ! -f "$ENV_FILE" ]; then
        print_warning ".env file not found. Creating from template..."
        cat > "$ENV_FILE" << 'EOF'
# FileOrganizer Environment Configuration
# Copy this file to .env and customize values

# ===========================================
# APPLICATION SETTINGS
# ===========================================
APP_NAME=FileOrganizer
DEBUG=false

# ===========================================
# DATABASE SETTINGS
# ===========================================
POSTGRES_USER=fileorganizer
POSTGRES_PASSWORD=change_this_secure_password
POSTGRES_DB=fileorganizer
DB_PORT=5432

# ===========================================
# API SETTINGS
# ===========================================
API_PORT=8000

# ===========================================
# OPENAI SETTINGS (Required for classification)
# ===========================================
# Get your API key from: https://platform.openai.com/api-keys
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4
EMBEDDING_MODEL=text-embedding-3-small

# ===========================================
# FILE PROCESSING
# ===========================================
MAX_FILE_SIZE_MB=50
EOF
        print_success "Created .env file. Please edit it with your configuration."
        print_warning "IMPORTANT: Set your OPENAI_API_KEY before starting!"
    else
        print_success ".env file exists"
    fi
}

# Build containers
build() {
    print_info "Building Docker containers..."
    docker compose -f "$COMPOSE_FILE" build "$@"
    print_success "Build completed"
}

# Start services
start() {
    print_info "Starting FileOrganizer services..."
    docker compose -f "$COMPOSE_FILE" up -d "$@"
    print_success "Services started"
    
    echo ""
    print_info "Waiting for services to be healthy..."
    sleep 5
    
    # Check health
    if curl -s http://localhost:${API_PORT:-8000}/health > /dev/null 2>&1; then
        print_success "Backend API is healthy"
        echo ""
        print_info "FileOrganizer is running at: http://localhost:${API_PORT:-8000}"
        print_info "API Documentation: http://localhost:${API_PORT:-8000}/docs"
    else
        print_warning "Backend may still be starting. Check logs with: ./deploy.sh logs"
    fi
}

# Stop services
stop() {
    print_info "Stopping FileOrganizer services..."
    docker compose -f "$COMPOSE_FILE" down "$@"
    print_success "Services stopped"
}

# Restart services
restart() {
    print_info "Restarting FileOrganizer services..."
    stop
    start
}

# View logs
logs() {
    docker compose -f "$COMPOSE_FILE" logs "$@"
}

# Show status
status() {
    print_info "Service Status:"
    docker compose -f "$COMPOSE_FILE" ps
    
    echo ""
    print_info "Health Checks:"
    
    # Check backend
    if curl -s http://localhost:${API_PORT:-8000}/health > /dev/null 2>&1; then
        print_success "Backend API: Healthy"
    else
        print_error "Backend API: Unhealthy or not running"
    fi
    
    # Check database
    if docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U ${POSTGRES_USER:-fileorganizer} > /dev/null 2>&1; then
        print_success "Database: Healthy"
    else
        print_error "Database: Unhealthy or not running"
    fi
}

# Clean up
clean() {
    print_warning "This will remove all containers, images, and volumes created by FileOrganizer."
    read -p "Are you sure? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose -f "$COMPOSE_FILE" down -v --remove-orphans "$@"
        print_success "Docker resources removed"
    else
        print_info "Cleanup aborted"
    fi
}

usage() {
    cat <<'EOF'
Usage: ./deploy.sh <command>

Commands:
  check       Validate local prerequisites (Docker, Compose, daemon)
  env         Create a .env file if missing
  build       Build container images
  start       Start the stack (runs check/env automatically)
  stop        Stop the stack (docker compose down)
  restart     Restart the stack
  status      Show container status and health checks
  logs        Tail docker compose logs (pass service names as args)
  clean       Remove containers, networks, and volumes (destructive)
EOF
}

case "${1:-}" in
    check)
        check_prerequisites
        ;;
    env)
        setup_env
        ;;
    build)
        check_prerequisites
        setup_env
        shift
        build "$@"
        ;;
    start)
        check_prerequisites
        setup_env
        shift
        start "$@"
        ;;
    stop)
        shift
        stop "$@"
        ;;
    restart)
        shift
        restart "$@"
        ;;
    status)
        status
        ;;
    logs)
        shift
        logs "$@"
        ;;
    clean)
        shift
        clean "$@"
        ;;
    ""|help|-h|--help)
        usage
        ;;
    *)
        print_error "Unknown command: $1"
        usage
        exit 1
        ;;
esac
