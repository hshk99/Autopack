"""Health checks for Autopack runtime (T0/T1 tiers).

These checks are lightweight and defensive: they never raise, but instead
return structured results so the executor can decide how to react.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal

from autopack.config import settings


@dataclass
class HealthCheckResult:
    """Result for a single health check."""

    check_name: str
    passed: bool
    message: str
    duration_ms: int


def _run_check(name: str, func) -> HealthCheckResult:
    """Helper to run a check and capture duration + exceptions."""
    start = time.time()
    try:
        passed, message = func()
    except Exception as e:  # Never let health checks crash the process
        passed = False
        message = f"Exception during {name}: {e}"
    duration_ms = int((time.time() - start) * 1000)
    return HealthCheckResult(
        check_name=name,
        passed=passed,
        message=message,
        duration_ms=duration_ms,
    )


# ============================================================================
# T0 Checks (quick, always safe to run)
# ============================================================================


def check_api_keys() -> HealthCheckResult:
    """Verify that at least one LLM provider API key is configured."""

    def _impl():
        glm = bool(os.getenv("GLM_API_KEY"))
        openai = bool(os.getenv("OPENAI_API_KEY"))
        anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
        gemini = bool(os.getenv("GOOGLE_API_KEY"))

        if glm or openai or anthropic or gemini:
            return True, (
                f"LLM keys present: GLM={glm}, OpenAI={openai}, "
                f"Anthropic={anthropic}, Gemini={gemini}"
            )
        return (
            False,
            "No LLM API keys set (GLM_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY).",
        )

    return _run_check("t0_api_keys", _impl)


def check_database(db_url: str | None = None) -> HealthCheckResult:
    """Basic database check: ensure we can connect to the configured DB.

    For sqlite URLs this just checks file/parent directory existence.
    """

    def _impl():
        # Use the same database URL as the API server / ORM layer
        url = db_url or settings.database_url
        if url.startswith("sqlite:///"):
            path = url.replace("sqlite:///", "", 1)
            p = Path(path)
            # Either file exists or parent directory is writable for creation
            if p.exists():
                return True, f"SQLite DB file exists at {p}."
            parent = p.parent or Path(".")
            if parent.exists() and os.access(parent, os.W_OK):
                return True, f"SQLite parent directory writable: {parent}."
            return False, f"SQLite parent directory not writable or missing: {parent}."

        # For non-sqlite URLs, we don't open a real connection here; just
        # verify that a URL is configured.
        return bool(url), f"DB URL configured: {url!r}"

    return _run_check("t0_database", _impl)


def check_workspace() -> HealthCheckResult:
    """Verify workspace path exists and is a git repo."""

    def _impl():
        workspace = Path(os.getenv("REPO_PATH", "."))  # Default: current dir
        if not workspace.exists():
            return False, f"Workspace path does not exist: {workspace}"

        git_dir = workspace / ".git"
        if not git_dir.exists():
            return False, f"Workspace is not a git repository (missing {git_dir})."

        return True, f"Workspace OK: {workspace} (git repo detected)."

    return _run_check("t0_workspace", _impl)


def check_config_files() -> HealthCheckResult:
    """Verify key config files exist and are readable."""

    def _impl():
        root = Path(".")
        required = [
            root / "config" / "models.yaml",
            root / "config" / "pricing.yaml",
        ]
        missing = [str(p) for p in required if not p.exists()]
        if missing:
            return False, f"Missing config files: {', '.join(missing)}"
        return True, "Core config files present (config/models.yaml, config/pricing.yaml)."

    return _run_check("t0_config_files", _impl)


def check_provider_connectivity() -> HealthCheckResult:
    """Minimal connectivity probe for configured providers."""

    def _impl():
        problems: List[str] = []

        # GLM via OpenAI-compatible client
        if os.getenv("GLM_API_KEY"):
            try:
                from openai import OpenAI  # type: ignore

                client = OpenAI(
                    api_key=os.getenv("GLM_API_KEY"),
                    base_url=os.getenv(
                        "GLM_API_BASE", "https://open.bigmodel.cn/api/paas/v4"
                    ),
                )
                client.chat.completions.create(
                    model="glm-4.6-20250101",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                )
            except Exception as e:
                problems.append(f"GLM connectivity error: {e}")

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI  # type: ignore

                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                )
            except Exception as e:
                problems.append(f"OpenAI connectivity error: {e}")

        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic  # type: ignore

                client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                )
            except Exception as e:
                problems.append(f"Anthropic connectivity error: {e}")

        # Gemini (only if library installed)
        if os.getenv("GOOGLE_API_KEY"):
            try:
                import google.generativeai as genai  # type: ignore

                genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                model = genai.GenerativeModel("gemini-2.5-pro")
                model.generate_content(
                    "ping", generation_config={"max_output_tokens": 1}
                )
            except ImportError:
                problems.append("Gemini client library google-generativeai not installed.")
            except Exception as e:
                problems.append(f"Gemini connectivity error: {e}")

        if problems:
            return False, "; ".join(problems)
        return True, "All configured providers responded to a minimal ping."

    return _run_check("t0_provider_connectivity", _impl)


# ============================================================================
# Entry point
# ============================================================================


def run_health_checks(tier: Literal["t0", "t1"] = "t0") -> List[HealthCheckResult]:
    """Run T0 or T1 health checks and return structured results."""
    checks: List[HealthCheckResult] = []

    if tier == "t0":
        checks.append(check_api_keys())
        checks.append(check_database())
        checks.append(check_workspace())
        checks.append(check_config_files())
        checks.append(check_provider_connectivity())
    # T1 checks (pytest, pip check, git clean/remote) can be added later as needed

    return checks


