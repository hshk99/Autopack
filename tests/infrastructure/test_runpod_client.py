"""Tests for RunPod GPU API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopack.infrastructure.runpod_client import (Pod, PodConfig, PodStatus,
                                                   RunPodClient)


class TestRunPodClientInitialization:
    """Test RunPodClient initialization."""

    def test_client_initialization_with_api_key(self):
        """Test client initialization with valid API key."""
        client = RunPodClient(api_key="test-key-123")
        assert client._api_key == "test-key-123"
        assert client._timeout == 30.0

    def test_client_initialization_without_api_key_raises_error(self):
        """Test client initialization without API key raises ValueError."""
        with pytest.raises(ValueError, match="API key is required"):
            RunPodClient(api_key="")

    def test_client_custom_timeout(self):
        """Test client initialization with custom timeout."""
        client = RunPodClient(api_key="test-key", timeout=60.0)
        assert client._timeout == 60.0


class TestPodDataStructures:
    """Test Pod and PodConfig data structures."""

    def test_pod_from_dict(self):
        """Test Pod creation from dictionary."""
        pod_data = {
            "pod_id": "pod-123",
            "name": "test-pod",
            "status": "running",
            "gpu_type": "A40",
            "gpu_count": 1,
            "cpu_cores": 4,
            "memory_gb": 20,
        }

        pod = Pod.from_dict(pod_data)

        assert pod.pod_id == "pod-123"
        assert pod.name == "test-pod"
        assert pod.status == PodStatus.RUNNING
        assert pod.gpu_type == "A40"
        assert pod.gpu_count == 1

    def test_pod_to_dict(self):
        """Test Pod conversion to dictionary."""
        pod = Pod(
            pod_id="pod-123",
            name="test-pod",
            status=PodStatus.RUNNING,
            gpu_type="A40",
            gpu_count=1,
        )

        pod_dict = pod.to_dict()

        assert pod_dict["pod_id"] == "pod-123"
        assert pod_dict["name"] == "test-pod"
        assert pod_dict["status"] == "running"
        assert pod_dict["gpu_type"] == "A40"

    def test_pod_config_to_dict(self):
        """Test PodConfig conversion to dictionary."""
        config = PodConfig(
            name="test-pod",
            gpu_type_id="a40",
            gpu_count=2,
        )

        config_dict = config.to_dict()

        assert config_dict["name"] == "test-pod"
        assert config_dict["gpu_type_id"] == "a40"
        assert config_dict["gpu_count"] == 2


class TestRunPodClientAsyncOperations:
    """Test async operations of RunPodClient."""

    @pytest.mark.asyncio
    async def test_create_pod_success(self):
        """Test successful pod creation."""
        client = RunPodClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "pod-123",
            "name": "test-pod",
            "status": "creating",
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            config = PodConfig(name="test-pod")
            result = await client.create_pod(config)

            assert result.success is True
            assert result.pod_id == "pod-123"
            assert "created successfully" in result.message

        await client.close()

    @pytest.mark.asyncio
    async def test_create_pod_failure(self):
        """Test failed pod creation."""
        client = RunPodClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Invalid configuration"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            config = PodConfig(name="test-pod")
            result = await client.create_pod(config)

            assert result.success is False
            assert "Failed to create pod" in result.message

        await client.close()

    @pytest.mark.asyncio
    async def test_list_pods_success(self):
        """Test successful pod listing."""
        client = RunPodClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pods": [
                {
                    "pod_id": "pod-123",
                    "name": "test-pod-1",
                    "status": "running",
                    "gpu_type": "A40",
                    "gpu_count": 1,
                },
                {
                    "pod_id": "pod-124",
                    "name": "test-pod-2",
                    "status": "exited",
                    "gpu_type": "RTX_4090",
                    "gpu_count": 2,
                },
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            pods, errors = await client.list_pods()

            assert len(pods) == 2
            assert pods[0].name == "test-pod-1"
            assert pods[1].name == "test-pod-2"
            assert len(errors) == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_delete_pod_success(self):
        """Test successful pod deletion."""
        client = RunPodClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient.delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response

            result = await client.delete_pod("pod-123")

            assert result.success is True
            assert "deleted successfully" in result.message

        await client.close()

    @pytest.mark.asyncio
    async def test_submit_job_success(self):
        """Test successful job submission."""
        client = RunPodClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "job-456",
            "status": "submitted",
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            job_spec = {"image": "ubuntu:latest", "command": "echo hello"}
            result = await client.submit_job("pod-123", job_spec)

            assert result.job_id == "job-456"
            assert result.status == "submitted"
            assert result.pod_id == "pod-123"

        await client.close()

    @pytest.mark.asyncio
    async def test_get_job_status_success(self):
        """Test successful job status retrieval."""
        client = RunPodClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "job-456",
            "status": "completed",
            "output": {"result": "success"},
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            job_data, error = await client.get_job_status("pod-123", "job-456")

            assert job_data is not None
            assert job_data["status"] == "completed"
            assert error is None

        await client.close()


class TestRunPodClientContextManager:
    """Test async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test using RunPodClient as async context manager."""
        async with RunPodClient(api_key="test-key") as client:
            assert client._api_key == "test-key"
