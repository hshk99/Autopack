"""
Create Autopack Run for Backend Test Fixes v2

Addresses the 35 test failures and 5 errors in tests/backend/:
1. Missing API endpoints (batch, search, auth) - returning 404
2. Password hashing bcrypt 72-byte limit
3. Australian document pack classification bugs
4. File validator missing Image import
5. Health check test assumptions
"""

import requests
import sys

API_URL = "http://localhost:8000"
RUN_ID = "fileorg-backend-fixes-v3-20251130"

TASKS = [
    # Tier 1: Core Infrastructure Fixes
    {
        "phase_id": "fix-password-hashing",
        "name": "Fix Password Hashing 72-byte Limit",
        "description": """Fix bcrypt 72-byte password limit issue in tests/backend/test_auth.py.

The tests use passwords longer than 72 bytes, but bcrypt only hashes the first 72 bytes.

Fix options:
1. Update test fixtures to use shorter passwords (under 72 chars)
2. Or modify src/backend/core/security.py to truncate/hash passwords before bcrypt

Current error:
ValueError: password cannot be longer than 72 bytes, truncate manually if necessary

Test files affected:
- tests/backend/test_auth.py (TestPasswordHashing, TestRegistrationEndpoint, TestLoginEndpoint)""",
        "tier_id": "T1-Infra",
        "tier_index": 0,
        "phase_index": 0,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_light",
    },
    {
        "phase_id": "fix-file-validator-import",
        "name": "Fix File Validator Image Import",
        "description": """Fix missing Image import in src/backend/services/file_validator.py.

The test expects an Image attribute but it's not exported properly.

Error:
AttributeError: <module 'src.backend.services.file_validator'> does not have the attribute 'Image'

Test file:
- tests/backend/services/test_file_validator.py::test_validate_image_content_invalid

Check if PIL.Image needs to be imported and exported, or if the test is checking the wrong attribute.""",
        "tier_id": "T1-Infra",
        "tier_index": 0,
        "phase_index": 1,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_light",
    },
    {
        "phase_id": "fix-health-check-tests",
        "name": "Fix Health Check Test Expectations",
        "description": """Fix health check tests in tests/backend/test_health.py.

Current failures:
1. test_health_check expects 'healthy' but gets 'degraded'
2. test_health_check_database_connection expects 'connected' or 'healthy' but gets 'disconnected'

The tests may have wrong assumptions about database state in test environment.

Options:
1. Update src/backend/api/health.py to handle TESTING=1 environment
2. Or update tests to use proper database fixtures
3. Or adjust test expectations for test environment""",
        "tier_id": "T1-Infra",
        "tier_index": 0,
        "phase_index": 2,
        "category": "testing",
        "complexity": "low",
        "builder_mode": "tweak_light",
    },
    # Tier 2: Australian Document Pack Fixes
    {
        "phase_id": "fix-postcode-validator",
        "name": "Fix Australian Postcode Validator",
        "description": """Fix postcode validation in src/backend/packs/australia_documents.py.

Failing test:
- TestPostcodeValidator::test_validate_postcode_invalid_range
- Expected: validate_postcode('9999') returns False
- Actual: returns True

Australian postcodes are 4 digits from 0200-9999, but 9999 is considered invalid in test.
Check the valid postcode ranges for Australia and fix the validation logic.""",
        "tier_id": "T2-Packs",
        "tier_index": 1,
        "phase_index": 0,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_light",
    },
    {
        "phase_id": "fix-ato-classifier",
        "name": "Fix ATO Tax Return Classification",
        "description": """Fix document classification in src/backend/packs/australia_documents.py.

Failing test:
- TestAustralianDocumentPack::test_classify_ato_tax_return
- Expected: classify() returns AustralianDocumentType.ATO_TAX_RETURN
- Actual: returns None

The classifier isn't detecting ATO tax return documents.
Check the classification logic and patterns for ATO tax returns.""",
        "tier_id": "T2-Packs",
        "tier_index": 1,
        "phase_index": 1,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "tweak_medium",
    },
    # Tier 3: Missing API Endpoints
    {
        "phase_id": "implement-search-endpoint",
        "name": "Implement Search API Endpoint",
        "description": """Implement the /api/search endpoint that returns 404.

Tests expecting this endpoint:
- tests/backend/api/test_search.py (16 tests)

Required functionality:
- GET /api/search with query params for filters
- Support: full_text, document_type, pack_name, confidence_range, date_range
- Support pagination: page, page_size
- Return proper validation errors (422) for invalid params
- Return search results with document data

Create or update src/backend/api/search.py router and register it in main.py.""",
        "tier_id": "T3-API",
        "tier_index": 2,
        "phase_index": 0,
        "category": "feature_scaffolding",
        "complexity": "high",
        "builder_mode": "scaffolding_heavy",
    },
    {
        "phase_id": "implement-batch-endpoint",
        "name": "Implement Batch Upload API Endpoint",
        "description": """Implement the /api/batch endpoint that returns 404.

Tests expecting this endpoint:
- tests/backend/api/test_batch.py (6 tests)

Required functionality:
- POST /api/batch for batch file upload
- Validate file types and batch size limits
- Return 202 for accepted, 400 for errors, 422 for validation errors
- GET /api/batch/{batch_id}/status (can return 501 Not Implemented initially)

Create or update src/backend/api/batch.py router and register it in main.py.""",
        "tier_id": "T3-API",
        "tier_index": 2,
        "phase_index": 1,
        "category": "feature_scaffolding",
        "complexity": "medium",
        "builder_mode": "scaffolding_medium",
    },
    {
        "phase_id": "implement-auth-endpoints",
        "name": "Implement Auth API Endpoints",
        "description": """Implement auth endpoints that return 404.

Tests expecting these endpoints:
- tests/backend/test_auth.py (registration and login tests)

Required functionality:
- POST /api/auth/register - create new user (201)
- POST /api/auth/login - authenticate user, return JWT (200)
- Return 401 for invalid credentials
- Return proper validation errors

Create or update src/backend/api/auth.py router and register it in main.py.""",
        "tier_id": "T3-API",
        "tier_index": 2,
        "phase_index": 2,
        "category": "feature_scaffolding",
        "complexity": "medium",
        "builder_mode": "scaffolding_medium",
    },
]


def create_run():
    """Create run with all tasks"""
    # Group tasks by tier
    tiers = {}
    for task in TASKS:
        tier_id = task["tier_id"]
        if tier_id not in tiers:
            tiers[tier_id] = {
                "tier_id": tier_id,
                "tier_index": task["tier_index"],
                "name": tier_id.split("-")[1],
                "description": f"Tier {task['tier_index'] + 1}",
                "phases": [],
            }
        tiers[tier_id]["phases"].append(
            {
                "phase_id": task["phase_id"],
                "phase_index": task["phase_index"],
                "tier_id": tier_id,
                "name": task["name"],
                "description": task["description"],
                "task_category": task["category"],
                "complexity": task["complexity"],
                "builder_mode": task["builder_mode"],
            }
        )

    # Flatten for API
    all_phases = []
    tier_list = []
    for tier in sorted(tiers.values(), key=lambda t: t["tier_index"]):
        all_phases.extend(tier["phases"])
        tier_list.append(
            {
                "tier_id": tier["tier_id"],
                "tier_index": tier["tier_index"],
                "name": tier["name"],
                "description": tier.get("description"),
            }
        )

    payload = {
        "run": {
            "run_id": RUN_ID,
            "safety_profile": "standard",
            "run_scope": "multi_tier",
            "token_cap": 200000,
            "max_phases": 10,
            "max_duration_minutes": 90,
        },
        "tiers": tier_list,
        "phases": all_phases,
    }

    print(f"[INFO] Creating run: {RUN_ID}")
    print(f"[INFO] Total tasks: {len(TASKS)}")
    print(f"[INFO] Total tiers: {len(tiers)}")

    response = requests.post(f"{API_URL}/runs/start", json=payload)

    if response.status_code != 201:
        print(f"[ERROR] Response: {response.status_code}")
        print(f"[ERROR] Body: {response.text}")

    response.raise_for_status()

    print(f"[SUCCESS] Run created: {RUN_ID}")
    print(f"[INFO] Run URL: {API_URL}/runs/{RUN_ID}")
    return response.json()


if __name__ == "__main__":
    try:
        result = create_run()
        print("\n[OK] Ready to execute autonomous run:")
        print(f"  python src/autopack/autonomous_executor.py --run-id {RUN_ID}")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Failed to create run: {e}")
        sys.exit(1)
