# Makefile Portability Notice (Delta 1.8)
# This Makefile requires Bash/Unix tools (rm, find, sleep, bash).
# On Windows, use one of:
#   - Git Bash: comes with Git for Windows
#   - WSL: Windows Subsystem for Linux
#   - MSYS2/MinGW: Unix-like environment
# Alternatively, run the equivalent commands directly:
#   - pip install -e ".[dev]"
#   - pytest tests/ -v
#   - docker-compose up -d / down / logs

.PHONY: help install test test-verbose docker-up docker-down docker-logs probe clean

help:
	@echo "Autopack Supervisor - Development Commands"
	@echo ""
	@echo "  make install         - Install dependencies"
	@echo "  make test            - Run unit tests"
	@echo "  make test-verbose    - Run unit tests with verbose output"
	@echo "  make docker-up       - Start Docker services"
	@echo "  make docker-down     - Stop Docker services"
	@echo "  make docker-logs     - View Docker logs"
	@echo "  make probe           - Run autonomous probe script"
	@echo "  make clean           - Clean up generated files"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

test-verbose:
	pytest tests/ -vv -s

docker-up:
	docker-compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

probe: docker-up
	@echo "Running autonomous probe script..."
	@bash scripts/autonomous_probe_run_state.sh

clean:
	rm -rf .autonomous_runs/
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
