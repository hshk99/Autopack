/**
 * API client for runs endpoints (GAP-8.10)
 * Uses shared apiFetch client for auth header injection and error handling
 */

import { apiFetch, extractErrorMessage } from './client';

export interface RunSummary {
  id: string;
  state: string;
  created_at: string;
  tokens_used: number;
  token_cap: number | null;
  phases_total: number;
  phases_completed: number;
  current_phase_name: string | null;
}

export interface RunsListResponse {
  runs: RunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface PhaseProgress {
  phase_id: string;
  name: string;
  state: string;
  phase_index: number;
  tokens_used: number | null;
  builder_attempts: number | null;
}

export interface RunProgress {
  run_id: string;
  state: string;
  started_at: string | null;
  completed_at: string | null;
  elapsed_seconds: number | null;
  tokens_used: number;
  token_cap: number | null;
  phases_total: number;
  phases_completed: number;
  phases_in_progress: number;
  phases_pending: number;
  phases: PhaseProgress[];
}

export interface Artifact {
  path: string;
  size_bytes: number;
  modified_at: string;
}

export interface ArtifactsIndexResponse {
  run_id: string;
  artifacts: Artifact[];
  total_size_bytes: number;
}

export interface BrowserArtifact {
  path: string;
  type: 'screenshot' | 'html';
  size_bytes: number;
  modified_at: string;
}

export interface BrowserArtifactsResponse {
  run_id: string;
  artifacts: BrowserArtifact[];
  total_count: number;
}

/**
 * Helper to normalize API errors with consistent formatting
 */
async function normalizeError(response: Response): Promise<Error> {
  const message = await extractErrorMessage(response);
  return new Error(`${response.status}: ${message}`);
}

export async function fetchRuns(
  limit: number = 20,
  offset: number = 0
): Promise<RunsListResponse> {
  const response = await apiFetch(
    `/runs?limit=${limit}&offset=${offset}`
  );
  if (!response.ok) {
    throw await normalizeError(response);
  }
  return response.json();
}

export async function fetchRunProgress(runId: string): Promise<RunProgress> {
  const response = await apiFetch(`/runs/${runId}/progress`);
  if (!response.ok) {
    throw await normalizeError(response);
  }
  return response.json();
}

export async function fetchArtifactsIndex(
  runId: string
): Promise<ArtifactsIndexResponse> {
  const response = await apiFetch(`/runs/${runId}/artifacts/index`);
  if (!response.ok) {
    throw await normalizeError(response);
  }
  return response.json();
}

export async function fetchArtifactFile(
  runId: string,
  path: string
): Promise<string> {
  const response = await apiFetch(
    `/runs/${runId}/artifacts/file?path=${encodeURIComponent(path)}`
  );
  if (!response.ok) {
    throw await normalizeError(response);
  }
  return response.text();
}

export async function fetchBrowserArtifacts(
  runId: string
): Promise<BrowserArtifactsResponse> {
  const response = await apiFetch(`/runs/${runId}/browser/artifacts`);
  if (!response.ok) {
    throw await normalizeError(response);
  }
  return response.json();
}
