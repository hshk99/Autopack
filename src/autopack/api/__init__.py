"""Autopack API package.

This package provides the FastAPI application structure.

Current structure:
- Main app is still in autopack.main (canonical entrypoint)
- Route shape contract testing is in tests/api/test_route_contract.py

Future refactoring (PR-03 roadmap):
- api/app.py: FastAPI app wiring
- api/deps.py: Shared dependencies (auth, rate limiting, db)
- api/routes/*.py: Domain routers (runs, phases, approvals, etc.)
"""
