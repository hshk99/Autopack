"""
Seed BUILD-129 Phase 3 Week 1 Telemetry Collection Run.
Diverse phases for stratified sampling.
"""
from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState

RUN_ID = "build129-p3-week1-telemetry"

def main():
    session = SessionLocal()
    try:
        # Delete existing
        existing_run = session.query(Run).filter(Run.id == RUN_ID).first()
        if existing_run:
            session.query(Phase).filter(Phase.run_id == RUN_ID).delete()
            session.query(Tier).filter(Tier.run_id == RUN_ID).delete()
            session.delete(existing_run)
            session.commit()

        # Create Run
        run = Run(
            id=RUN_ID,
            state=RunState.QUEUED,
            safety_profile="normal",
            run_scope="multi_tier",
            token_cap=500000,
            max_phases=12,
            max_duration_minutes=480,
            goal_anchor="BUILD-129 Phase 3: Week 1 Stratified Telemetry Collection"
        )
        session.add(run)
        session.flush()
        print(f"[OK] Created run: {RUN_ID}")

        # Create tier
        tier = Tier(
            tier_id="build129-p3-week1-tier",
            run_id=RUN_ID,
            name="Week 1: Diverse Categories",
            tier_index=0,
            description="Collect diverse telemetry samples across categories, complexities, and deliverable counts"
        )
        session.add(tier)
        session.flush()
        tier_db_id = tier.id

        # Define phases - targeting gaps in current dataset
        phases = [
            {
                "id": "build129-p3-w1.1-backend-high-6files",
                "name": "Backend Circuit Breaker (High Complexity, 6 Files)",
                "desc": "High complexity backend with multiple files for circuit breaker pattern",
                "category": "backend",
                "complexity": "high",
                "deliverables": [
                    "src/autopack/circuit_breaker/__init__.py",
                    "src/autopack/circuit_breaker/breaker.py",
                    "src/autopack/circuit_breaker/state_machine.py",
                    "src/autopack/circuit_breaker/metrics.py",
                    "tests/autopack/circuit_breaker/test_breaker.py",
                    "tests/autopack/circuit_breaker/test_state_machine.py"
                ]
            },
            {
                "id": "build129-p3-w1.2-testing-medium-4files",
                "name": "Test Suite for Package Detector (Medium Complexity, 4 Files)",
                "desc": "Comprehensive test coverage for package detection module",
                "category": "testing",
                "complexity": "medium",
                "deliverables": [
                    "tests/autopack/diagnostics/test_package_detector_basic.py",
                    "tests/autopack/diagnostics/test_package_detector_edge_cases.py",
                    "tests/autopack/diagnostics/test_package_detector_integration.py",
                    "tests/autopack/diagnostics/fixtures/package_scenarios.py"
                ]
            },
            {
                "id": "build129-p3-w1.3-database-high-5files",
                "name": "Database Migration for Telemetry Schema (High Complexity, 5 Files)",
                "desc": "Add telemetry tables with indexes and constraints",
                "category": "database",
                "complexity": "high",
                "deliverables": [
                    "alembic/versions/20251224_add_telemetry_tables.py",
                    "src/autopack/models/telemetry.py",
                    "src/autopack/telemetry/collector.py",
                    "tests/autopack/models/test_telemetry.py",
                    "tests/autopack/telemetry/test_collector.py"
                ]
            },
            {
                "id": "build129-p3-w1.4-frontend-medium-3files",
                "name": "Frontend Component for Error Display (Medium Complexity, 3 Files)",
                "desc": "React component with hooks and state management",
                "category": "frontend",
                "complexity": "medium",
                "deliverables": [
                    "src/frontend/components/ErrorDisplay.tsx",
                    "src/frontend/hooks/useErrorState.ts",
                    "tests/frontend/components/ErrorDisplay.test.tsx"
                ]
            },
            {
                "id": "build129-p3-w1.5-refactoring-high-7files",
                "name": "Refactor File Organization (High Complexity, 7 Files)",
                "desc": "Large refactoring to reorganize file structure",
                "category": "refactoring",
                "complexity": "high",
                "deliverables": [
                    "src/autopack/file_manifest/organizer.py",
                    "src/autopack/file_manifest/classifier.py",
                    "src/autopack/file_manifest/validator.py",
                    "src/autopack/file_manifest/utils.py",
                    "tests/autopack/file_manifest/test_organizer.py",
                    "tests/autopack/file_manifest/test_classifier.py",
                    "tests/autopack/file_manifest/test_validator.py"
                ]
            },
            {
                "id": "build129-p3-w1.6-deployment-medium-3files",
                "name": "Docker Configuration for Dev Environment (Medium Complexity, 3 Files)",
                "desc": "Docker setup with compose and environment configuration",
                "category": "deployment",
                "complexity": "medium",
                "deliverables": [
                    "docker/Dockerfile.dev",
                    "docker/docker-compose.dev.yml",
                    "docs/deployment/DEV_SETUP.md"
                ]
            },
            {
                "id": "build129-p3-w1.7-configuration-medium-4files",
                "name": "Configuration Management System (Medium Complexity, 4 Files)",
                "desc": "Environment-based configuration with validation",
                "category": "configuration",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/config/manager.py",
                    "src/autopack/config/validators.py",
                    "config/defaults.yaml",
                    "tests/autopack/config/test_manager.py"
                ]
            },
            {
                "id": "build129-p3-w1.8-integration-high-5files",
                "name": "Integration with External API (High Complexity, 5 Files)",
                "desc": "Full integration with authentication, retry logic, and error handling",
                "category": "integration",
                "complexity": "high",
                "deliverables": [
                    "src/autopack/integrations/external_api.py",
                    "src/autopack/integrations/auth_manager.py",
                    "src/autopack/integrations/retry_handler.py",
                    "tests/autopack/integrations/test_external_api.py",
                    "tests/autopack/integrations/test_auth_manager.py"
                ]
            },
            {
                "id": "build129-p3-w1.9-documentation-low-5files",
                "name": "Documentation for Token Estimator (Low Complexity, 5 Files)",
                "desc": "Comprehensive documentation with examples and guides",
                "category": "documentation",
                "complexity": "low",
                "deliverables": [
                    "docs/token_estimator/OVERVIEW.md",
                    "docs/token_estimator/USAGE_GUIDE.md",
                    "docs/token_estimator/API_REFERENCE.md",
                    "docs/token_estimator/EXAMPLES.md",
                    "docs/token_estimator/FAQ.md"
                ]
            },
            {
                "id": "build129-p3-w1.10-backend-low-3files",
                "name": "Simple Utility Functions (Low Complexity, 3 Files)",
                "desc": "Basic utility functions with tests",
                "category": "backend",
                "complexity": "low",
                "deliverables": [
                    "src/autopack/utils/string_helpers.py",
                    "src/autopack/utils/date_helpers.py",
                    "tests/autopack/utils/test_helpers.py"
                ]
            },
            {
                "id": "build129-p3-w1.11-testing-high-6files",
                "name": "E2E Test Suite (High Complexity, 6 Files)",
                "desc": "End-to-end testing framework with fixtures and utilities",
                "category": "testing",
                "complexity": "high",
                "deliverables": [
                    "tests/e2e/test_full_workflow.py",
                    "tests/e2e/test_api_integration.py",
                    "tests/e2e/fixtures/test_data.py",
                    "tests/e2e/fixtures/mock_responses.py",
                    "tests/e2e/utils/test_helpers.py",
                    "tests/e2e/conftest.py"
                ]
            },
            {
                "id": "build129-p3-w1.12-refactoring-low-3files",
                "name": "Code Cleanup (Low Complexity, 3 Files)",
                "desc": "Simple refactoring to improve code quality",
                "category": "refactoring",
                "complexity": "low",
                "deliverables": [
                    "src/autopack/models/__init__.py",
                    "src/autopack/database.py",
                    "src/autopack/constants.py"
                ]
            }
        ]

        for idx, pd in enumerate(phases, 1):
            scope = {"deliverables": pd["deliverables"], "paths": [], "read_only_context": []}
            phase = Phase(
                phase_id=pd["id"],
                run_id=RUN_ID,
                tier_id=tier_db_id,
                phase_index=idx,
                name=pd["name"],
                description=pd["desc"],
                scope=scope,
                state=PhaseState.QUEUED,
                task_category=pd["category"],
                complexity=pd["complexity"]
            )
            session.add(phase)
            print(f"[OK] Phase {idx}: {pd['id']} ({pd['category']}/{pd['complexity']}, {len(pd['deliverables'])} deliverables)")

        session.commit()
        print(f"\n✅ Week 1 telemetry collection run seeded!")
        print(f"Run: PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" python -m autopack.autonomous_executor --run-id {RUN_ID}")
        print(f"\nExpected diversity:")
        print(f"  Categories: backend(2), testing(2), database(1), frontend(1), refactoring(2), deployment(1), configuration(1), integration(1), documentation(1)")
        print(f"  Complexity: low(3), medium(4), high(5)")
        print(f"  Deliverables: 3 files(5), 4 files(2), 5 files(3), 6 files(2), 7 files(1)")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()
