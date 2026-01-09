/**
 * Centralized API client for Autopack frontend
 *
 * GAP-8.10.x implementation
 */

import type {
  Run,
  DashboardRunStatus,
  RunListResponse,
  RunArtifacts,
  BrowserArtifact,
  ApiError,
} from '../types';

const API_BASE = '/api';

/**
 * Generic fetch wrapper with error handling
 */
async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    try {
      const errorData: ApiError = await response.json();
      errorDetail = errorData.detail || errorDetail;
    } catch {
      // Ignore JSON parse errors
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

// === Run Endpoints ===

/**
 * Get list of runs (for inbox view)
 * Note: This endpoint may need to be added to the backend
 */
export async function listRuns(limit = 50, offset = 0): Promise<RunListResponse> {
  return apiFetch<RunListResponse>(`/runs?limit=${limit}&offset=${offset}`);
}

/**
 * Get run details by ID
 */
export async function getRun(runId: string): Promise<Run> {
  return apiFetch<Run>(`/runs/${runId}`);
}

/**
 * Get dashboard status for a run
 */
export async function getRunStatus(runId: string): Promise<DashboardRunStatus> {
  return apiFetch<DashboardRunStatus>(`/dashboard/runs/${runId}/status`);
}

// === Artifact Endpoints (GAP-8.10.1) ===

/**
 * Get run artifacts (plan, summaries, logs, completion report)
 * Note: This endpoint may need to be added to the backend
 */
export async function getRunArtifacts(runId: string): Promise<RunArtifacts> {
  return apiFetch<RunArtifacts>(`/runs/${runId}/artifacts`);
}

/**
 * Get run errors
 */
export async function getRunErrors(runId: string): Promise<{
  run_id: string;
  error_count: number;
  errors: unknown[];
}> {
  return apiFetch(`/runs/${runId}/errors`);
}

/**
 * Get run error summary
 */
export async function getRunErrorSummary(runId: string): Promise<{
  run_id: string;
  summary: string;
}> {
  return apiFetch(`/runs/${runId}/errors/summary`);
}

// === Browser Artifact Endpoints (GAP-8.10.3) ===

/**
 * Get browser artifacts for a run (screenshots, HAR, video, traces)
 * Note: This endpoint may need to be added to the backend
 */
export async function getBrowserArtifacts(runId: string): Promise<BrowserArtifact[]> {
  return apiFetch<BrowserArtifact[]>(`/runs/${runId}/browser-artifacts`);
}

/**
 * Get download URL for a specific artifact
 */
export function getArtifactDownloadUrl(runId: string, artifactId: string): string {
  return `${API_BASE}/runs/${runId}/artifacts/${artifactId}/download`;
}

// === Consolidated Metrics ===

/**
 * Get consolidated token metrics for a run
 */
export async function getConsolidatedMetrics(
  runId: string,
  limit = 1000,
  offset = 0
): Promise<unknown> {
  return apiFetch(`/dashboard/runs/${runId}/consolidated-metrics?limit=${limit}&offset=${offset}`);
}

// === Health ===

/**
 * Check API health
 */
export async function healthCheck(): Promise<{
  status: string;
  version: string;
  database: { connected: boolean };
}> {
  return apiFetch('/health');
}
