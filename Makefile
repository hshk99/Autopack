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

.PHONY: help install test test-verbose test-docs test-api test-llm test-fast docker-up docker-down docker-logs probe clean

help:
	@echo "Autopack Supervisor - Development Commands"
	@echo ""
	@echo "  make install         - Install dependencies"
	@echo ""
	@echo "Fast local gates (5.3.5 - run before PR):"
	@echo "  make test-docs       - Docs/SOT gate (fast, always run first)"
	@echo "  make test-api        - API fast gate (no Postgres required)"
	@echo "  make test-llm        - LLM wiring fast gate"
	@echo "  make test-fast       - All fast gates combined (docs + api + llm)"
	@echo ""
	@echo "Full test runs:"
	@echo "  make test            - Run unit tests"
	@echo "  make test-verbose    - Run unit tests with verbose output"
	@echo ""
	@echo "Docker:"
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

# Fast local gates (5.3.5) - run before PR to get quick signal
test-docs:
	@echo "Running docs/SOT gate (fast, always run first)..."
	python -m pytest -q tests/docs/

test-api:
	@echo "Running API fast gate (no Postgres)..."
	python -m pytest -q tests/api/

test-llm:
	@echo "Running LLM wiring fast gate..."
	python -m pytest -q tests/llm_service/

test-fast: test-docs test-api test-llm
	@echo "All fast gates passed!"

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
