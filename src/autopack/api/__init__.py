"""Autopack API package.

This package provides the FastAPI application structure.

Current structure:
- Main app is still in autopack.main (canonical entrypoint)
- Route shape contract testing is in tests/api/test_route_contract.py

Extracted modules (PR-API-1+):
- api/deps.py: Auth + rate limiting dependencies (PR-API-1) ✅
- api/app.py: FastAPI app wiring (lifespan, middleware, exception handler) (PR-API-2) ✅

Future refactoring (PR-API-3+):
- api/routes/*.py: Domain routers (runs, phases, approvals, etc.)
"""
