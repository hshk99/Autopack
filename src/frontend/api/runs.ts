/**
 * API client for runs endpoints (GAP-8.10)
 */

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

const API_BASE = '/api';

export async function fetchRuns(
  limit: number = 20,
  offset: number = 0
): Promise<RunsListResponse> {
  const response = await fetch(
    `${API_BASE}/runs?limit=${limit}&offset=${offset}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch runs: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchRunProgress(runId: string): Promise<RunProgress> {
  const response = await fetch(`${API_BASE}/runs/${runId}/progress`);
  if (!response.ok) {
    throw new Error(`Failed to fetch run progress: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchArtifactsIndex(
  runId: string
): Promise<ArtifactsIndexResponse> {
  const response = await fetch(`${API_BASE}/runs/${runId}/artifacts/index`);
  if (!response.ok) {
    throw new Error(`Failed to fetch artifacts: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchArtifactFile(
  runId: string,
  path: string
): Promise<string> {
  const response = await fetch(
    `${API_BASE}/runs/${runId}/artifacts/file?path=${encodeURIComponent(path)}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch artifact file: ${response.statusText}`);
  }
  return response.text();
}

export async function fetchBrowserArtifacts(
  runId: string
): Promise<BrowserArtifactsResponse> {
  const response = await fetch(`${API_BASE}/runs/${runId}/browser/artifacts`);
  if (!response.ok) {
    throw new Error(
      `Failed to fetch browser artifacts: ${response.statusText}`
    );
  }
  return response.json();
}
