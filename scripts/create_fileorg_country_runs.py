"""
Create Phase 2 country-pack runs for FileOrganizer (UK, Canada, Australia).

Each run scopes the YAML packs + docs, wires the backend pytest suite inside
`.autonomous_runs/file-organizer-app-v1/fileorganizer/backend`, and enforces
the acceptance criteria from `FUTURE_PLAN.md` Task 4–6.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
API_KEY = os.getenv("AUTOPACK_API_KEY")

WORKDIR = ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend"
COMMON_CI = {
    "type": "pytest",
    "workdir": WORKDIR,
    "paths": ["tests"],
    "args": ["-vv"],
    "env": {
        "PYTHONPATH": ".",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    },
    "timeout_seconds": 600,
    "log_name": "packs_pytest.log",
    "success_message": "Pack loader tests passed",
    "failure_message": "Pack loader tests failed",
}

COUNTRY_CONFIG: Dict[str, Dict] = {
    "uk": {
        "phase_id": "fileorg-p2-country-uk",
        "name": "UK Pack Templates",
        "description": """Create UK-specific templates for tax and immigration packs.
Goals:
- Research HMRC + Home Office evidence requirements
- Generate tax_uk.yaml and immigration_uk.yaml with categories/examples
- Update consolidated reference docs with UK pack instructions
- Verify load_pack.py + pytest tests/test_packs.py -k uk
""",
        "scope_paths": [
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/tax_uk.yaml",
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/immigration_uk.yaml",
            ".autonomous_runs/file-organizer-app-v1/archive/CONSOLIDATED_REFERENCE.md",
        ],
        "read_only": [
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/tax_generic.yaml",
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/immigration_generic.yaml",
            ".autonomous_runs/file-organizer-app-v1/docs/research/superseded/",
        ],
        "ci_args": ["-k", "uk"],
    },
    "canada": {
        "phase_id": "fileorg-p2-country-canada",
        "name": "Canada Pack Templates",
        "description": """Create CRA + IRCC-aligned templates for Canadian packs.
Goals mirror UK task but focus on bilingual labels (EN/FR) and CRA document codes.
""",
        "scope_paths": [
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/tax_canada.yaml",
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/immigration_canada.yaml",
            ".autonomous_runs/file-organizer-app-v1/archive/CONSOLIDATED_REFERENCE.md",
        ],
        "read_only": [
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/tax_generic.yaml",
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/immigration_generic.yaml",
            ".autonomous_runs/file-organizer-app-v1/docs/research/superseded/",
        ],
        "ci_args": ["-k", "canada"],
    },
    "australia": {
        "phase_id": "fileorg-p2-country-australia",
        "name": "Australia Pack Templates",
        "description": """Add ATO + Department of Home Affairs templates (tax & immigration).
Capture residency tests, visa subclasses, and bridging-visa evidence.
""",
        "scope_paths": [
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/tax_australia.yaml",
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/immigration_australia.yaml",
            ".autonomous_runs/file-organizer-app-v1/archive/CONSOLIDATED_REFERENCE.md",
        ],
        "read_only": [
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/tax_generic.yaml",
            ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/packs/immigration_generic.yaml",
            ".autonomous_runs/file-organizer-app-v1/docs/research/superseded/",
        ],
        "ci_args": ["-k", "australia"],
    },
}


def build_phase(country: str) -> Dict:
    config = COUNTRY_CONFIG[country]
    ci_spec = dict(COMMON_CI)
    ci_spec["args"] = COMMON_CI["args"] + config.get("ci_args", [])

    return {
        "phase_id": config["phase_id"],
        "phase_index": 0,
        "tier_id": f"tier-country-{country}",
        "name": config["name"],
        "description": config["description"],
        "task_category": "backend",
        # Treat pack authoring as high complexity so Builder isn't constrained by the "small fix" churn guard.
        "complexity": "high",
        "builder_mode": "full_file",
        # Pack templates frequently exceed the 30% churn gate despite being single-file edits.
        # Force large_refactor classification so Builder can replace the YAML safely.
        "change_size": "large_refactor",
        # YAML pack generation legitimately adds hundreds of lines at once.
        # Allow mass addition so the growth guard does not block full rewrites.
        "allow_mass_addition": True,
        "scope": {
            "paths": config["scope_paths"],
            "read_only_context": config["read_only"],
        },
        "ci": ci_spec,
    }


def build_tier(country: str) -> Dict:
    config = COUNTRY_CONFIG[country]
    return {
        "tier_id": f"tier-country-{country}",
        "tier_index": 0,
        "name": f"{config['name']} Tier",
        "description": f"Country-specific pack templates for {country.title()}",
    }


def create_run(country: str) -> None:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"fileorg-country-{country}-{timestamp}"

    payload = {
        "run": {
            "run_id": run_id,
            "run_type": "project_build",
            "safety_profile": "normal",
            "run_scope": "single_tier",
            "token_cap": 60000,
            "max_phases": 1,
            "max_duration_minutes": 60,
        },
        "tiers": [build_tier(country)],
        "phases": [build_phase(country)],
    }

    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    print(f"[INFO] Creating FileOrganizer country run ({country}): {run_id}")
    try:
        response = requests.post(
            f"{API_URL}/runs/start",
            json=payload,
            headers=headers or None,
            timeout=30,
        )
        if response.status_code != 201:
            print(f"[ERROR] Response: {response.status_code}")
            print(f"[ERROR] Body: {response.text}")
            sys.exit(1)

        print(f"[SUCCESS] Run created: {run_id}")
        print(f"[INFO] Run URL: {API_URL}/runs/{run_id}")
        print(
            "  Execute with (from repo root):\n"
            f"    PYTHONPATH=src python src/autopack/autonomous_executor.py "
            f"--run-id {run_id} --run-type project_build --stop-on-first-failure --verbose\n"
        )
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Cannot reach API at {API_URL}")
        print(
            "       Start the FastAPI server first: python -m uvicorn autopack.main:app --port 8000"
        )
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Failed to create run: {exc}")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create FileOrganizer country pack runs (UK, Canada, Australia)."
    )
    parser.add_argument(
        "--country",
        choices=sorted(COUNTRY_CONFIG.keys()),
        help="Country to target (default: uk)",
        default="uk",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Create runs for all configured countries",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    targets: List[str]
    if args.all:
        targets = list(COUNTRY_CONFIG.keys())
    else:
        targets = [args.country]

    for country in targets:
        create_run(country)
