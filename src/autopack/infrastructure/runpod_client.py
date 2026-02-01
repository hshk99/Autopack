"""RunPod API client for provisioning GPU pods.

Provides interfaces for creating, managing, and deleting RunPod GPU pods
suitable for generative AI model inference and training workloads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class PodStatus(Enum):
    """Status of a RunPod pod."""

    CREATING = "creating"
    RUNNING = "running"
    PAUSED = "paused"
    EXITED = "exited"
    TERMINATING = "terminating"
    ERROR = "error"
    UNKNOWN = "unknown"


class GPUType(Enum):
    """GPU types available on RunPod."""

    A100 = "A100"
    A40 = "A40"
    RTX_A6000 = "RTX_A6000"
    RTX_4090 = "RTX_4090"
    RTX_4080 = "RTX_4080"
    RTX_3090 = "RTX_3090"
    L40S = "L40S"
    H100 = "H100"


@dataclass
class Pod:
    """Represents a RunPod GPU pod."""

    pod_id: str
    name: str
    status: PodStatus = PodStatus.UNKNOWN
    gpu_type: Optional[str] = None
    gpu_count: int = 0
    cpu_cores: int = 0
    memory_gb: int = 0
    container_disk_gb: int = 0
    volume_gb: int = 0
    cost_per_hour: float = 0.0
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ports: List[Dict[str, Any]] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    container_image: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "pod_id": self.pod_id,
            "name": self.name,
            "status": self.status.value,
            "gpu_type": self.gpu_type,
            "gpu_count": self.gpu_count,
            "cpu_cores": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "container_disk_gb": self.container_disk_gb,
            "volume_gb": self.volume_gb,
            "cost_per_hour": self.cost_per_hour,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ports": self.ports,
            "environment": self.environment,
            "container_image": self.container_image,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Pod:
        """Create Pod from dictionary."""
        status = PodStatus.UNKNOWN
        if "status" in data:
            try:
                status = PodStatus(data["status"])
            except ValueError:
                pass

        created_at = None
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        started_at = None
        if data.get("started_at"):
            try:
                started_at = datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return cls(
            pod_id=data.get("pod_id", ""),
            name=data.get("name", ""),
            status=status,
            gpu_type=data.get("gpu_type"),
            gpu_count=data.get("gpu_count", 0),
            cpu_cores=data.get("cpu_cores", 0),
            memory_gb=data.get("memory_gb", 0),
            container_disk_gb=data.get("container_disk_gb", 0),
            volume_gb=data.get("volume_gb", 0),
            cost_per_hour=data.get("cost_per_hour", 0.0),
            created_at=created_at,
            started_at=started_at,
            ports=data.get("ports", []),
            environment=data.get("environment", {}),
            container_image=data.get("container_image", ""),
        )


@dataclass
class PodConfig:
    """Configuration for creating a new RunPod pod."""

    name: str
    image: str = "nvidia/cuda:12.0.0-runtime-ubuntu22.04"
    gpu_type_id: str = "a40"  # Default to A40 GPUs
    gpu_count: int = 1
    cpu_cores: int = 4
    memory_gb: int = 20
    container_disk_gb: int = 20
    volume_gb: int = 0
    environment: Dict[str, str] = field(default_factory=dict)
    ports: Optional[str] = None
    volume_mount_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API request."""
        return {
            "name": self.name,
            "image": self.image,
            "gpu_type_id": self.gpu_type_id,
            "gpu_count": self.gpu_count,
            "cpu_cores": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "container_disk_gb": self.container_disk_gb,
            "volume_gb": self.volume_gb,
            "environment": self.environment,
            "ports": self.ports,
            "volume_mount_path": self.volume_mount_path,
        }


@dataclass
class JobResult:
    """Result of a job submission to RunPod."""

    job_id: str
    pod_id: str
    status: str = "submitted"
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class OperationResult:
    """Result of an operation on a RunPod pod."""

    success: bool
    message: str = ""
    pod_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)


class RunPodClient:
    """Client for RunPod GPU API.

    Manages GPU pods suitable for generative AI inference and training.
    Provides cost-effective GPU compute with pay-as-you-go pricing.

    API Pricing (approximate):
    - A40 (1x): $0.35-0.50/hour
    - RTX 4090 (1x): $0.30-0.45/hour
    - A100 (1x): $0.60-1.00/hour
    - H100 (1x): $1.50-2.50/hour
    """

    API_BASE = "https://api.runpod.io/graphql"
    API_ENDPOINT = "https://api.runpod.io/v1"

    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        """Initialize RunPod client.

        Args:
            api_key: RunPod API key.
            timeout: Request timeout in seconds.
        """
        if not api_key:
            raise ValueError("API key is required")

        self._api_key = api_key
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx async client."""
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                "api_key": self._api_key,
            }
            self._client = httpx.AsyncClient(headers=headers, timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> RunPodClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def create_pod(self, config: PodConfig) -> OperationResult:
        """Create a new RunPod pod.

        Args:
            config: Pod configuration.

        Returns:
            OperationResult with pod creation status.
        """
        try:
            client = await self._get_client()
            url = f"{self.API_ENDPOINT}/pods"
            payload = config.to_dict()

            response = await client.post(url, json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                pod_id = data.get("id") or data.get("pod_id")

                logger.info(f"Pod created: {config.name} (ID: {pod_id})")
                return OperationResult(
                    success=True,
                    message=f"Pod {config.name} created successfully",
                    pod_id=pod_id,
                )
            else:
                error_msg = response.json().get("message", "Unknown error")
                logger.error(f"Failed to create pod: {error_msg}")
                return OperationResult(
                    success=False,
                    message=f"Failed to create pod: {error_msg}",
                    errors=[error_msg],
                )
        except httpx.HTTPError as e:
            logger.error(f"HTTP error creating pod: {e}")
            return OperationResult(
                success=False,
                message=f"HTTP error: {str(e)}",
                errors=[str(e)],
            )
        except Exception as e:
            logger.error(f"Unexpected error creating pod: {e}")
            return OperationResult(
                success=False,
                message=f"Unexpected error: {str(e)}",
                errors=[str(e)],
            )

    async def list_pods(self) -> tuple[List[Pod], List[str]]:
        """List all RunPod pods.

        Returns:
            Tuple of (pods list, errors list).
        """
        pods: List[Pod] = []
        errors: List[str] = []

        try:
            client = await self._get_client()
            url = f"{self.API_ENDPOINT}/pods"

            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                for pod_data in data.get("pods", []):
                    pod = Pod.from_dict(pod_data)
                    pods.append(pod)
                logger.info(f"Retrieved {len(pods)} pods")
            else:
                error_msg = response.json().get("message", "Unknown error")
                logger.error(f"Failed to list pods: {error_msg}")
                errors.append(error_msg)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error listing pods: {e}")
            errors.append(str(e))
        except Exception as e:
            logger.error(f"Unexpected error listing pods: {e}")
            errors.append(str(e))

        return pods, errors

    async def get_pod(self, pod_id: str) -> tuple[Optional[Pod], Optional[str]]:
        """Get a specific pod by ID.

        Args:
            pod_id: Pod ID.

        Returns:
            Tuple of (Pod or None, error message or None).
        """
        try:
            client = await self._get_client()
            url = f"{self.API_ENDPOINT}/pods/{pod_id}"

            response = await client.get(url)

            if response.status_code == 200:
                pod_data = response.json()
                pod = Pod.from_dict(pod_data)
                logger.info(f"Retrieved pod: {pod.name}")
                return pod, None
            else:
                error_msg = response.json().get("message", "Pod not found")
                logger.warning(f"Failed to get pod {pod_id}: {error_msg}")
                return None, error_msg

        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting pod: {e}")
            return None, str(e)
        except Exception as e:
            logger.error(f"Unexpected error getting pod: {e}")
            return None, str(e)

    async def delete_pod(self, pod_id: str) -> OperationResult:
        """Delete a RunPod pod.

        Args:
            pod_id: Pod ID to delete.

        Returns:
            OperationResult with deletion status.
        """
        try:
            client = await self._get_client()
            url = f"{self.API_ENDPOINT}/pods/{pod_id}"

            response = await client.delete(url)

            if response.status_code in (200, 204):
                logger.info(f"Pod deleted: {pod_id}")
                return OperationResult(
                    success=True,
                    message=f"Pod {pod_id} deleted successfully",
                    pod_id=pod_id,
                )
            else:
                error_data = response.json()
                error_msg = error_data.get("message", "Unknown error")
                logger.error(f"Failed to delete pod: {error_msg}")
                return OperationResult(
                    success=False,
                    message=f"Failed to delete pod: {error_msg}",
                    errors=[error_msg],
                )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error deleting pod: {e}")
            return OperationResult(
                success=False,
                message=f"HTTP error: {str(e)}",
                errors=[str(e)],
            )
        except Exception as e:
            logger.error(f"Unexpected error deleting pod: {e}")
            return OperationResult(
                success=False,
                message=f"Unexpected error: {str(e)}",
                errors=[str(e)],
            )

    async def submit_job(self, pod_id: str, job_spec: Dict[str, Any]) -> JobResult:
        """Submit a job to a RunPod pod.

        Args:
            pod_id: Pod ID to submit job to.
            job_spec: Job specification dictionary.

        Returns:
            JobResult with submission status.
        """
        try:
            client = await self._get_client()
            url = f"{self.API_ENDPOINT}/pods/{pod_id}/jobs"

            response = await client.post(url, json=job_spec)

            if response.status_code in (200, 201):
                data = response.json()
                job_id = data.get("id") or data.get("job_id")

                logger.info(f"Job submitted to pod {pod_id} (Job ID: {job_id})")
                return JobResult(
                    job_id=job_id,
                    pod_id=pod_id,
                    status="submitted",
                )
            else:
                error_msg = response.json().get("message", "Unknown error")
                logger.error(f"Failed to submit job: {error_msg}")
                return JobResult(
                    job_id="",
                    pod_id=pod_id,
                    status="failed",
                    error=error_msg,
                )
        except httpx.HTTPError as e:
            logger.error(f"HTTP error submitting job: {e}")
            return JobResult(
                job_id="",
                pod_id=pod_id,
                status="failed",
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Unexpected error submitting job: {e}")
            return JobResult(
                job_id="",
                pod_id=pod_id,
                status="failed",
                error=str(e),
            )

    async def get_job_status(
        self, pod_id: str, job_id: str
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Get status of a job on a RunPod pod.

        Args:
            pod_id: Pod ID.
            job_id: Job ID.

        Returns:
            Tuple of (job status dict or None, error message or None).
        """
        try:
            client = await self._get_client()
            url = f"{self.API_ENDPOINT}/pods/{pod_id}/jobs/{job_id}"

            response = await client.get(url)

            if response.status_code == 200:
                job_data = response.json()
                logger.info(f"Retrieved job status: {job_id}")
                return job_data, None
            else:
                error_msg = response.json().get("message", "Job not found")
                logger.warning(f"Failed to get job status {job_id}: {error_msg}")
                return None, error_msg

        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting job status: {e}")
            return None, str(e)
        except Exception as e:
            logger.error(f"Unexpected error getting job status: {e}")
            return None, str(e)
