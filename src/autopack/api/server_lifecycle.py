"""API server lifecycle management for Autopack.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles starting, monitoring, and stopping the Autopack API server.
"""

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Optional, cast
from urllib.parse import urlparse

from autopack.config import settings

try:
    import resource
except ImportError:
    # resource module is not available on Windows
    resource = None  # type: ignore

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


def set_subprocess_resource_limits(max_memory_mb: int = 2000, max_cpu_seconds: int = 300) -> None:
    """Set resource limits for subprocess execution.

    These limits prevent resource exhaustion from malicious or runaway code.

    Args:
        max_memory_mb: Maximum memory in MB (default 2GB for API server)
        max_cpu_seconds: Maximum CPU time in seconds (default 5 minutes)
    """
    if resource is None:
        # resource module not available (e.g., Windows)
        logger.debug("Resource limits not available on this platform")
        return

    res = cast(Any, resource)  # type: ignore
    try:
        # Set virtual memory limit (soft limit - warning, hard limit - hard stop)
        memory_bytes = max_memory_mb * 1024 * 1024
        res.setrlimit(res.RLIMIT_AS, (memory_bytes, memory_bytes))
        logger.debug(f"Set memory limit to {max_memory_mb}MB")
    except (OSError, ValueError) as e:
        # May not be available on all systems
        logger.debug(f"Could not set memory limit: {e}")

    try:
        # Set CPU time limit
        res.setrlimit(res.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds))
        logger.debug(f"Set CPU time limit to {max_cpu_seconds}s")
    except (OSError, ValueError) as e:
        logger.debug(f"Could not set CPU time limit: {e}")


class APIServerLifecycle:
    """Manages API server lifecycle.

    Responsibilities:
    1. Start API server process
    2. Monitor server health
    3. Handle server crashes
    4. Stop server gracefully
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor
        self.server_process: Optional[subprocess.Popen] = None
        self.log_file_handle: Optional[IO] = None

    def ensure_server_running(self) -> bool:
        """Ensure API server is running.

        Starts server if not running, checks health if running.

        Returns:
            True if server is running and healthy
        """
        # Parse API URL
        parsed = urlparse(self.executor.api_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8000

        # Check if server is already running
        try:
            payload = self.executor.api_client.check_health(timeout=2.0)
            # BUILD-129 Phase 3: /health should reflect DB readiness too (see src/autopack/main.py).
            # Require that the service identify itself as the Autopack Supervisor API.
            # This prevents false positives when another service is listening on the same port
            # (e.g., src/backend FastAPI which has /health but not the supervisor API contract).
            if payload.get("service") != "autopack":
                logger.error(
                    "A service responded on /health but did not identify as the Autopack Supervisor API "
                    f"(service={payload.get('service')!r}). Refusing to use it."
                )
                return False

            if payload.get("db_ok") is False or payload.get("status") not in (
                None,
                "healthy",
            ):
                logger.warning(
                    "API server responded to /health but reported unhealthy DB. "
                    "Executor requires a healthy API+DB; will attempt to start a local API server."
                )
            else:
                logger.info("API server is already running")
                return True
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug(f"API server health check failed (expected if not running): {e}")
        except Exception as e:
            logger.debug(f"Unexpected error checking API server health: {e}")

        # Try to connect to port to see if something is listening
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex((host, port))
            if result == 0:
                # Port is open but /health failed - likely a different service or a broken API.
                # Do NOT assume it's usable; this causes opaque 500s later.
                logger.error(
                    f"Port {port} is open but {self.executor.api_url}/health is not healthy. "
                    "Another service may be using the port, or the API is misconfigured. "
                    "Stop the conflicting process or set AUTOPACK_API_URL to a different port."
                )
                return False
        except OSError as e:
            logger.debug(f"Socket connection check failed for {host}:{port}: {e}")
        finally:
            sock.close()

        # Server not running - try to start it
        return self.start_server(host, port)

    def start_server(self, host: str, port: int) -> bool:
        """Start API server process.

        Args:
            host: Host to bind to (overridden by settings.autopack_bind_address)
            port: Port to bind to

        Returns:
            True if server started successfully
        """
        # IMP-SEC-001: Use explicit bind address from settings instead of deriving from URL
        # This prevents accidental exposure when DATABASE_URL contains a non-local host
        bind_host = settings.autopack_bind_address
        if bind_host != host:
            logger.info(
                f"Using explicit bind address '{bind_host}' from settings "
                f"(original host from URL: '{host}')"
            )
            host = bind_host

        logger.info(
            f"API server not detected at {self.executor.api_url}, attempting to start it..."
        )

        try:
            # Configurable startup wait (Windows + cold start can exceed 10s).
            # Default: 30s. Override with AUTOPACK_API_STARTUP_TIMEOUT_SECONDS.
            try:
                startup_timeout_s = int(os.getenv("AUTOPACK_API_STARTUP_TIMEOUT_SECONDS", "30"))
            except (ValueError, TypeError) as e:
                logger.debug(
                    f"Invalid AUTOPACK_API_STARTUP_TIMEOUT_SECONDS, using default 30s: {e}"
                )
                startup_timeout_s = 30
            startup_timeout_s = max(5, min(300, startup_timeout_s))

            # Ensure the uvicorn subprocess can import `autopack.*` from `src/`.
            # NOTE: modifying sys.path in this process does NOT affect the subprocess.
            env = os.environ.copy()
            try:
                src_path = str((Path(self.executor.workspace).resolve() / "src"))
                existing = env.get("PYTHONPATH", "")
                if src_path and (src_path not in existing.split(os.pathsep)):
                    env["PYTHONPATH"] = src_path + (os.pathsep + existing if existing else "")
            except (OSError, ValueError) as e:
                logger.debug(f"Could not set PYTHONPATH for subprocess: {e}")
            env.setdefault("PYTHONUTF8", "1")

            # Capture uvicorn logs for RCA (previously discarded to DEVNULL).
            log_dir = Path(".autonomous_runs") / self.executor.run_id / "diagnostics"
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.debug(f"Could not create diagnostics log directory {log_dir}: {e}")
            api_log_path = log_dir / f"api_server_{host}_{port}.log"
            log_fp = None
            try:
                try:
                    log_fp = open(api_log_path, "ab")
                    self.log_file_handle = log_fp
                except OSError as e:
                    logger.debug(f"Could not open API server log file {api_log_path}: {e}")
                    log_fp = None

                api_cmd = [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    # IMPORTANT: module path is relative to PYTHONPATH=src; 'src.autopack...' is not importable
                    # because 'src/' is not a Python package (no src/__init__.py).
                    "autopack.main:app",
                    "--host",
                    host,
                    "--port",
                    str(port),
                ]

                # Start process in background (detached on Windows)
                if sys.platform == "win32":
                    # Windows: use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS
                    # Note: Resource limits not available on Windows via preexec_fn
                    process = subprocess.Popen(
                        api_cmd,
                        stdout=log_fp or subprocess.DEVNULL,
                        stderr=log_fp or subprocess.DEVNULL,
                        env=env,
                        cwd=str(Path(self.executor.workspace).resolve()),
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                        | subprocess.DETACHED_PROCESS,
                    )
                else:
                    # Unix: use nohup-like behavior with resource limits
                    process = subprocess.Popen(
                        api_cmd,
                        stdout=log_fp or subprocess.DEVNULL,
                        stderr=log_fp or subprocess.DEVNULL,
                        env=env,
                        cwd=str(Path(self.executor.workspace).resolve()),
                        start_new_session=True,
                        preexec_fn=lambda: set_subprocess_resource_limits(
                            max_memory_mb=2000, max_cpu_seconds=300
                        ),
                    )

                self.server_process = process

                # Wait a bit for server to start
                return self.check_server_health(
                    host, port, startup_timeout_s, api_log_path, process
                )
            finally:
                # Always close file handle after subprocess has inherited it (or on failure)
                # The subprocess maintains its own reference to the file descriptor
                if log_fp is not None:
                    try:
                        log_fp.close()
                    except OSError as e:
                        logger.debug(f"Could not close log file handle: {e}")
                    self.log_file_handle = None

        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            logger.info("Please start the API server manually:")
            logger.info(
                f"  (ensure PYTHONPATH=src) python -m uvicorn autopack.main:app --host {host} --port {port}"
            )
            return False

    def check_server_health(
        self,
        host: str,
        port: int,
        timeout_s: int,
        log_path: Path,
        process: subprocess.Popen,
    ) -> bool:
        """Check if server is responding to health checks.

        Args:
            host: Host server is bound to
            port: Port server is bound to
            timeout_s: Maximum seconds to wait for startup
            log_path: Path to server log file
            process: Server subprocess

        Returns:
            True if server is healthy
        """
        logger.info(f"Waiting for API server to start on {host}:{port}...")
        for i in range(timeout_s):  # Wait up to configured seconds
            time.sleep(1)

            # If the server process exits early, surface the log path.
            try:
                if process.poll() is not None:
                    logger.error(
                        f"API server process exited early (code={process.returncode}). "
                        f"See log: {log_path}"
                    )
                    return False
            except OSError as e:
                logger.debug(f"Could not poll process status: {e}")
            try:
                self.executor.api_client.check_health(timeout=1)
                logger.info("✅ API server started successfully")
                # Optional: fail fast if the API is healthy but the run is missing (common DB drift symptom).
                if os.getenv("AUTOPACK_SKIP_RUN_EXISTENCE_CHECK") != "1":
                    from autopack.supervisor.api_client import SupervisorApiHttpError

                    try:
                        self.executor.api_client.get_run(self.executor.run_id, timeout=2)
                    except SupervisorApiHttpError as e:
                        if e.status_code == 404:
                            logger.error(
                                "[DB_MISMATCH] API is healthy but run was not found. "
                                f"run_id={self.executor.run_id!r}. This usually means the API and executor are "
                                "pointed at different SQLite files (cwd/relative path drift) or the run was not seeded "
                                "into this DATABASE_URL."
                            )
                            # Hint: enable DEBUG_DB_IDENTITY=1 and re-check /health payload.
                            logger.error(
                                "Hint: set DEBUG_DB_IDENTITY=1 and re-check /health for sqlite_file + run counts."
                            )
                            return False
                    except Exception as _e:
                        logger.warning(f"Run existence check skipped due to error: {_e}")
                return True
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.debug(f"Health check attempt {i + 1}/{timeout_s} failed: {e}")
            if i < timeout_s - 1:
                logger.info(f"  Still waiting... ({i + 1}/{timeout_s})")

        logger.error(f"API server failed to start within {timeout_s} seconds (log: {log_path})")
        return False

    def stop_server(self) -> None:
        """Stop API server gracefully with timeout enforcement."""
        if self.server_process:
            try:
                # Attempt graceful shutdown with 30 second timeout
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=30)
                    logger.info("API server stopped gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    logger.warning("API server did not stop within 30 seconds, force killing...")
                    self.server_process.kill()
                    try:
                        self.server_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.error("API server could not be killed")
            except Exception as e:
                logger.warning(f"Failed to stop API server: {e}")
            finally:
                self.server_process = None

        # Close any remaining log file handle
        if self.log_file_handle is not None:
            try:
                self.log_file_handle.close()
            except Exception as e:
                logger.warning(f"Failed to close log file handle: {e}")
            finally:
                self.log_file_handle = None
