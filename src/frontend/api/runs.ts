/**
 * API client for runs endpoints (GAP-8.10.x)
 *
 * Provides typed fetch functions for:
 * - GET /runs (list)
 * - GET /runs/{run_id}/artifacts/index
 * - GET /runs/{run_id}/artifacts/file
 * - GET /runs/{run_id}/browser/artifacts
 * - GET /runs/{run_id}/progress
 */

// Types matching backend schemas

export interface RunSummary {
  id: string;
  state: string;
  created_at: string;
  updated_at: string | null;
  tokens_used: number;
  token_cap: number | null;
  phases_total: number;
  phases_completed: number;
  current_phase_name: string | null;
}

export interface RunListResponse {
  runs: RunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ArtifactInfo {
  path: string;
  size_bytes: number;
  modified_at: string;
  is_directory: boolean;
}

export interface ArtifactsIndexResponse {
  run_id: string;
  artifacts: ArtifactInfo[];
  total_size_bytes: number;
}

export interface BrowserArtifact {
  artifact_id: string;
  path: string;
  artifact_class: string;
  created_at: string;
  size_bytes: number;
  session_id: string;
}

export interface BrowserArtifactsResponse {
  run_id: string;
  artifacts: BrowserArtifact[];
  total_count: number;
}

export interface PhaseProgressInfo {
  phase_id: string;
  name: string;
  state: string;
  tier_id: string;
  phase_index: number;
  tokens_used: number | null;
  builder_attempts: number | null;
}

export interface RunProgressResponse {
  run_id: string;
  state: string;
  tokens_used: number;
  token_cap: number | null;
  phases_total: number;
  phases_completed: number;
  phases_in_progress: number;
  phases_pending: number;
  phases: PhaseProgressInfo[];
  started_at: string | null;
  elapsed_seconds: number | null;
}

// API base URL - proxied through Vite in development
const API_BASE = '/api';

/**
 * Fetch list of runs with pagination
 */
export async function fetchRuns(
  limit: number = 20,
  offset: number = 0
): Promise<RunListResponse> {
  const response = await fetch(
    `${API_BASE}/runs?limit=${limit}&offset=${offset}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch runs: ${response.status}`);
  }
  return response.json();
}

/**
 * Fetch artifacts index for a run
 */
export async function fetchArtifactsIndex(
  runId: string
): Promise<ArtifactsIndexResponse> {
  const response = await fetch(`${API_BASE}/runs/${runId}/artifacts/index`);
  if (!response.ok) {
    throw new Error(`Failed to fetch artifacts: ${response.status}`);
  }
  return response.json();
}

/**
 * Get URL for fetching a specific artifact file
 */
export function getArtifactFileUrl(runId: string, path: string): string {
  return `${API_BASE}/runs/${runId}/artifacts/file?path=${encodeURIComponent(
    path
  )}`;
}

/**
 * Fetch browser artifacts for a run
 */
export async function fetchBrowserArtifacts(
  runId: string
): Promise<BrowserArtifactsResponse> {
  const response = await fetch(`${API_BASE}/runs/${runId}/browser/artifacts`);
  if (!response.ok) {
    throw new Error(`Failed to fetch browser artifacts: ${response.status}`);
  }
  return response.json();
}

/**
 * Fetch run progress
 */
export async function fetchRunProgress(
  runId: string
): Promise<RunProgressResponse> {
  const response = await fetch(`${API_BASE}/runs/${runId}/progress`);
  if (!response.ok) {
    throw new Error(`Failed to fetch run progress: ${response.status}`);
  }
  return response.json();
}
