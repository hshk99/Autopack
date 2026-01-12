"""Context preflight validation module for executor startup checks.

Extracted from autonomous_executor.py for PR-EXE-5.
Provides pre-execution validation and infrastructure checks:
- API server health and connectivity checks
- Stale phase detection and reset
- Startup configuration validation
- Database schema validation
"""

import logging
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


@dataclass
class PreflightResult:
    """Result of a preflight check.

    Attributes:
        success: Whether the check passed
        message: Description of the result
        error: Error message if failed
        details: Additional details dictionary
    """
    success: bool
    message: str
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class ApiHealthResult:
    """Result of API health check.

    Attributes:
        healthy: Whether the API is healthy and usable
        service_name: Name of the service (should be 'autopack')
        db_ok: Whether the database is healthy
        error: Error description if unhealthy
    """
    healthy: bool
    service_name: Optional[str] = None
    db_ok: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class StalePhaseInfo:
    """Information about a detected stale phase.

    Attributes:
        phase_id: Phase identifier
        last_updated: When the phase was last updated
        stale_duration: How long the phase has been stale
        reset_success: Whether reset to QUEUED succeeded
    """
    phase_id: str
    last_updated: Optional[datetime] = None
    stale_duration: Optional[timedelta] = None
    reset_success: bool = False


def check_api_health(api_url: str, timeout: int = 2) -> ApiHealthResult:
    """Check if API server is healthy and usable.

    Validates that:
    1. The /health endpoint responds with 200
    2. The service identifies as 'autopack'
    3. The database is healthy (if reported)

    Args:
        api_url: Base URL of the API server
        timeout: Request timeout in seconds

    Returns:
        ApiHealthResult with health status
    """
    try:
        response = requests.get(f"{api_url}/health", timeout=timeout)

        if response.status_code != 200:
            return ApiHealthResult(
                healthy=False,
                error=f"Health check returned status {response.status_code}",
            )

        try:
            payload = response.json()

            # Require that the service identify itself as the Autopack Supervisor API
            service_name = payload.get("service")
            if service_name != "autopack":
                return ApiHealthResult(
                    healthy=False,
                    service_name=service_name,
                    error=f"Unexpected service: {service_name!r} (expected 'autopack')",
                )

            # Check database health if reported
            db_ok = payload.get("db_ok")
            status = payload.get("status")

            if db_ok is False or status not in (None, "healthy"):
                return ApiHealthResult(
                    healthy=False,
                    service_name=service_name,
                    db_ok=db_ok,
                    error="API reported unhealthy DB status",
                )

            return ApiHealthResult(
                healthy=True,
                service_name=service_name,
                db_ok=db_ok,
            )

        except Exception:
            return ApiHealthResult(
                healthy=False,
                error="Health endpoint did not return valid JSON",
            )

    except requests.exceptions.Timeout:
        return ApiHealthResult(healthy=False, error="Health check timed out")
    except requests.exceptions.ConnectionError:
        return ApiHealthResult(healthy=False, error="Could not connect to API server")
    except Exception as e:
        return ApiHealthResult(healthy=False, error=str(e))


def check_port_open(host: str, port: int) -> bool:
    """Check if a port is open (something is listening).

    Args:
        host: Hostname to check
        port: Port number to check

    Returns:
        True if port is open, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex((host, port))
            return result == 0
        except Exception:
            return False
        finally:
            sock.close()
    except Exception:
        return False


def check_run_exists(api_url: str, run_id: str, timeout: int = 2) -> PreflightResult:
    """Check if a run exists in the database.

    Args:
        api_url: Base URL of the API server
        run_id: Run identifier to check
        timeout: Request timeout in seconds

    Returns:
        PreflightResult with existence status
    """
    try:
        response = requests.get(f"{api_url}/runs/{run_id}", timeout=timeout)

        if response.status_code == 200:
            return PreflightResult(success=True, message="Run exists in database")

        if response.status_code == 404:
            return PreflightResult(
                success=False,
                message="Run not found in database",
                error="DB_MISMATCH: Run was not found. API and executor may be using different databases.",
            )

        return PreflightResult(
            success=False,
            message=f"Unexpected status code: {response.status_code}",
            error=f"Failed to verify run existence: HTTP {response.status_code}",
        )

    except Exception as e:
        return PreflightResult(
            success=False,
            message="Could not verify run existence",
            error=str(e),
        )


def start_api_server(
    workspace: Path,
    run_id: str,
    host: str = "localhost",
    port: int = 8000,
    startup_timeout: int = 30,
) -> Tuple[bool, Optional[str]]:
    """Start the API server in background.

    Args:
        workspace: Workspace path for the server
        run_id: Run ID for log directory
        host: Host to bind to
        port: Port to bind to
        startup_timeout: Maximum seconds to wait for startup

    Returns:
        Tuple of (success, error_message)
    """
    # Create log directory
    log_dir = Path(".autonomous_runs") / run_id / "diagnostics"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    api_log_path = log_dir / f"api_server_{host}_{port}.log"

    # Set up environment with PYTHONPATH
    env = os.environ.copy()
    try:
        src_path = str((Path(workspace).resolve() / "src"))
        existing = env.get("PYTHONPATH", "")
        if src_path and (src_path not in existing.split(os.pathsep)):
            env["PYTHONPATH"] = src_path + (os.pathsep + existing if existing else "")
    except Exception:
        pass
    env.setdefault("PYTHONUTF8", "1")

    # Build uvicorn command
    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "autopack.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]

    log_fp = None
    try:
        log_fp = open(api_log_path, "ab")
    except Exception:
        pass

    try:
        # Start process based on platform
        if sys.platform == "win32":
            process = subprocess.Popen(
                api_cmd,
                stdout=log_fp or subprocess.DEVNULL,
                stderr=log_fp or subprocess.DEVNULL,
                env=env,
                cwd=str(Path(workspace).resolve()),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            )
        else:
            process = subprocess.Popen(
                api_cmd,
                stdout=log_fp or subprocess.DEVNULL,
                stderr=log_fp or subprocess.DEVNULL,
                env=env,
                cwd=str(Path(workspace).resolve()),
                start_new_session=True,
            )

        api_url = f"http://{host}:{port}"

        # Wait for server to start
        for i in range(startup_timeout):
            time.sleep(1)

            # Check if process exited early
            try:
                if process.poll() is not None:
                    return False, f"API server exited early (code={process.returncode}). Log: {api_log_path}"
            except Exception:
                pass

            # Check health
            health = check_api_health(api_url, timeout=1)
            if health.healthy:
                return True, None

            if i < startup_timeout - 1:
                logger.info(f"  Still waiting for API server... ({i+1}/{startup_timeout})")

        return False, f"API server failed to start within {startup_timeout}s. Log: {api_log_path}"

    except Exception as e:
        return False, str(e)
    finally:
        if log_fp:
            try:
                log_fp.close()
            except Exception:
                pass


def ensure_api_server_running(
    api_url: str,
    workspace: Path,
    run_id: str,
    startup_timeout: Optional[int] = None,
    skip_run_check: bool = False,
) -> PreflightResult:
    """Ensure the API server is running, starting it if necessary.

    Args:
        api_url: API URL to check/use
        workspace: Workspace path for starting server
        run_id: Run ID for logging and verification
        startup_timeout: Override startup timeout (default from env or 30s)
        skip_run_check: Skip run existence verification

    Returns:
        PreflightResult with status
    """
    # Parse API URL
    parsed = urlparse(api_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000

    # Get startup timeout from environment or default
    if startup_timeout is None:
        try:
            startup_timeout = int(os.getenv("AUTOPACK_API_STARTUP_TIMEOUT_SECONDS", "30"))
        except Exception:
            startup_timeout = 30
        startup_timeout = max(5, min(300, startup_timeout))

    # Check if server is already running and healthy
    health = check_api_health(api_url)

    if health.healthy:
        logger.info("API server is already running")

        # Optionally verify run exists
        if not skip_run_check and os.getenv("AUTOPACK_SKIP_RUN_EXISTENCE_CHECK") != "1":
            run_check = check_run_exists(api_url, run_id)
            if not run_check.success:
                logger.error(f"[DB_MISMATCH] {run_check.error}")
                return PreflightResult(
                    success=False,
                    message="Run not found in database",
                    error=run_check.error,
                )

        return PreflightResult(success=True, message="API server is healthy")

    # Check if port is in use by something else
    if check_port_open(host, port):
        return PreflightResult(
            success=False,
            message="Port in use by incompatible service",
            error=f"Port {port} is open but /health is not healthy. "
                  f"Another service may be using the port.",
        )

    # Try to start the server
    logger.info(f"API server not detected at {api_url}, attempting to start it...")

    success, error = start_api_server(
        workspace=workspace,
        run_id=run_id,
        host=host,
        port=port,
        startup_timeout=startup_timeout,
    )

    if success:
        logger.info("✅ API server started successfully")

        # Verify run exists after startup
        if not skip_run_check and os.getenv("AUTOPACK_SKIP_RUN_EXISTENCE_CHECK") != "1":
            run_check = check_run_exists(api_url, run_id)
            if not run_check.success:
                logger.error(f"[DB_MISMATCH] {run_check.error}")
                return PreflightResult(
                    success=False,
                    message="Run not found in database",
                    error=run_check.error,
                )

        return PreflightResult(success=True, message="API server started successfully")

    return PreflightResult(
        success=False,
        message="Failed to start API server",
        error=error,
    )


def detect_stale_phases(
    run_data: Dict[str, Any],
    stale_threshold_minutes: int = 10,
) -> List[StalePhaseInfo]:
    """Detect phases stuck in EXECUTING state.

    Args:
        run_data: Run data from API with tiers/phases
        stale_threshold_minutes: Minutes after which a phase is considered stale

    Returns:
        List of detected stale phases
    """
    stale_phases = []
    stale_threshold = timedelta(minutes=stale_threshold_minutes)
    now = datetime.now()

    tiers = run_data.get("tiers", [])

    for tier in tiers:
        phases = tier.get("phases", [])

        for phase in phases:
            if phase.get("state") != "EXECUTING":
                continue

            phase_id = phase.get("phase_id")
            last_updated_str = phase.get("updated_at") or phase.get("last_updated")

            if not last_updated_str:
                # No timestamp - assume stale
                stale_phases.append(StalePhaseInfo(
                    phase_id=phase_id,
                    last_updated=None,
                    stale_duration=None,
                ))
                continue

            try:
                # Parse timestamp
                last_updated = datetime.fromisoformat(
                    last_updated_str.replace("Z", "+00:00")
                )

                # Make timezone-naive for comparison
                if last_updated.tzinfo:
                    last_updated = last_updated.replace(tzinfo=None)

                time_stale = now - last_updated

                if time_stale > stale_threshold:
                    stale_phases.append(StalePhaseInfo(
                        phase_id=phase_id,
                        last_updated=last_updated,
                        stale_duration=time_stale,
                    ))

            except Exception as e:
                logger.warning(
                    f"[{phase_id}] Failed to parse timestamp '{last_updated_str}': {e}"
                )

    return stale_phases


def reset_stale_phase(
    phase_id: str,
    update_fn: Callable[[str, str], bool],
) -> bool:
    """Reset a stale phase to QUEUED state.

    Args:
        phase_id: Phase identifier
        update_fn: Function to update phase status (phase_id, new_status) -> success

    Returns:
        True if reset succeeded
    """
    try:
        success = update_fn(phase_id, "QUEUED")
        if success:
            logger.info(f"[{phase_id}] Successfully reset to QUEUED")
        return success
    except Exception as e:
        logger.error(f"[{phase_id}] Failed to reset stale phase: {e}")
        return False


def run_startup_checks(
    check_configs: List[Dict[str, Any]],
) -> PreflightResult:
    """Run proactive startup checks from configuration.

    Args:
        check_configs: List of check configurations with:
            - name: Check name
            - check: Check function returning bool
            - fix: Optional fix function
            - priority: Priority level (HIGH/MEDIUM/LOW)
            - reason: Why this check exists

    Returns:
        PreflightResult summarizing check results
    """
    checks_passed = 0
    checks_failed = 0
    fixes_applied = 0

    for check_config in check_configs:
        check_name = check_config.get("name")
        check_fn = check_config.get("check")
        fix_fn = check_config.get("fix")
        priority = check_config.get("priority", "MEDIUM")
        reason = check_config.get("reason", "")

        # Skip placeholder checks
        if check_fn == "implemented_in_executor":
            continue

        logger.info(f"[{priority}] Checking: {check_name}")
        if reason:
            logger.info(f"  Reason: {reason}")

        try:
            if callable(check_fn):
                passed = check_fn()
            else:
                continue

            if not passed:
                checks_failed += 1
                logger.warning("  Check FAILED - applying proactive fix...")
                if callable(fix_fn):
                    try:
                        fix_fn()
                        fixes_applied += 1
                        logger.info("  Fix applied successfully")
                    except Exception as e:
                        logger.warning(f"  Fix failed: {e}")
                else:
                    logger.warning("  No fix function available")
            else:
                checks_passed += 1
                logger.info("  Check PASSED")

        except Exception as e:
            checks_failed += 1
            logger.warning(f"  Startup check failed with error: {e}")

    return PreflightResult(
        success=checks_failed == 0 or fixes_applied > 0,
        message=f"Startup checks complete: {checks_passed} passed, {checks_failed} failed, {fixes_applied} fixes applied",
        details={
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
            "fixes_applied": fixes_applied,
        },
    )


def validate_schema_on_startup(database_url: Optional[str] = None) -> PreflightResult:
    """Validate database schema on startup.

    BUILD-130: Schema validation on startup (fail-fast if schema invalid).

    Args:
        database_url: Database URL to validate (uses config if not provided)

    Returns:
        PreflightResult with validation status
    """
    try:
        from autopack.schema_validator import SchemaValidator

        if database_url is None:
            from autopack.config import get_database_url
            database_url = get_database_url()

        if not database_url:
            logger.warning(
                "[SchemaValidator] No database URL found - skipping schema validation"
            )
            return PreflightResult(
                success=True,
                message="Schema validation skipped - no database URL",
            )

        validator = SchemaValidator(database_url)
        schema_result = validator.validate_on_startup()

        if not schema_result.is_valid:
            error_count = len(schema_result.errors)
            logger.error("[FATAL] Schema validation failed on startup!")
            logger.error(f"[FATAL] Found {error_count} schema violations")
            logger.error("[FATAL] Run: python scripts/break_glass_repair.py diagnose")

            return PreflightResult(
                success=False,
                message=f"Schema validation failed: {error_count} violations",
                error="Run 'python scripts/break_glass_repair.py diagnose' to see details",
                details={"error_count": error_count},
            )

        return PreflightResult(
            success=True,
            message="Schema validation passed",
        )

    except ImportError as e:
        logger.warning(f"[SchemaValidator] Schema validator not available: {e}")
        return PreflightResult(
            success=True,
            message="Schema validation skipped - validator not available",
        )
    except Exception as e:
        logger.warning(f"[SchemaValidator] Schema validation failed: {e}")
        return PreflightResult(
            success=False,
            message="Schema validation error",
            error=str(e),
        )


def validate_token_config(config_path: Optional[Path] = None) -> PreflightResult:
    """Validate token_soft_caps configuration at startup.

    Per GPT_RESPONSE26: Validate token_soft_caps configuration at startup.

    Args:
        config_path: Path to models.yaml (default: config/models.yaml)

    Returns:
        PreflightResult with validation status
    """
    try:
        import yaml

        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "models.yaml"

        if not config_path.exists():
            return PreflightResult(
                success=True,
                message="Config validation skipped - models.yaml not found",
            )

        with open(config_path) as f:
            config = yaml.safe_load(f)

        from autopack.config_loader import validate_token_soft_caps
        validate_token_soft_caps(config)

        return PreflightResult(
            success=True,
            message="Token config validation passed",
        )

    except Exception as e:
        logger.debug(f"[Config] Startup validation skipped: {e}")
        return PreflightResult(
            success=True,
            message=f"Config validation skipped: {e}",
        )
