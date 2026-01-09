/**
 * TypeScript type definitions matching backend Pydantic schemas
 *
 * GAP-8.10.x implementation
 */

// === Run Types ===

export type RunState =
  | 'QUEUED'
  | 'PLAN_BOOTSTRAP'
  | 'RUN_CREATED'
  | 'PHASE_QUEUEING'
  | 'PHASE_EXECUTION'
  | 'GATE'
  | 'CI_RUNNING'
  | 'SNAPSHOT_CREATED'
  | 'DONE_SUCCESS'
  | 'DONE_FAILED_BUDGET_EXHAUSTED'
  | 'DONE_FAILED_POLICY_VIOLATION'
  | 'DONE_FAILED_REQUIRES_HUMAN_REVIEW'
  | 'DONE_FAILED_ENVIRONMENT';

export type TierState = 'PENDING' | 'IN_PROGRESS' | 'COMPLETE' | 'FAILED' | 'SKIPPED';

export type PhaseState =
  | 'QUEUED'
  | 'EXECUTING'
  | 'GATE'
  | 'CI_RUNNING'
  | 'COMPLETE'
  | 'FAILED'
  | 'SKIPPED';

export interface Run {
  id: string;
  state: RunState;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
  safety_profile: string;
  run_scope: string;
  token_cap: number;
  max_phases: number;
  max_duration_minutes: number;
  tokens_used: number;
  ci_runs_used: number;
  minor_issues_count: number;
  major_issues_count: number;
  promotion_eligible_to_main: string;
  failure_reason?: string;
  goal_anchor?: string;
  tiers?: Tier[];
}

export interface Tier {
  id: number;
  tier_id: string;
  run_id: string;
  tier_index: number;
  name: string;
  description?: string;
  state: TierState;
  token_cap?: number;
  ci_run_cap?: number;
  max_minor_issues_tolerated?: number;
  max_major_issues_tolerated: number;
  tokens_used: number;
  ci_runs_used: number;
  minor_issues_count: number;
  major_issues_count: number;
  cleanliness: string;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
  phases?: Phase[];
}

export interface Phase {
  id: number;
  phase_id: string;
  run_id: string;
  tier_id: number;
  phase_index: number;
  name: string;
  description?: string;
  state: PhaseState;
  task_category?: string;
  complexity?: string;
  builder_mode?: string;
  scope?: PhaseScope;
  max_builder_attempts?: number;
  max_auditor_attempts?: number;
  incident_token_cap?: number;
  builder_attempts: number;
  auditor_attempts: number;
  tokens_used: number;
  minor_issues_count: number;
  major_issues_count: number;
  issue_state: string;
  quality_level?: string;
  quality_blocked: boolean;
  retry_attempt: number;
  revision_epoch: number;
  escalation_level: number;
  last_attempt_timestamp?: string;
  last_failure_reason?: string;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface PhaseScope {
  paths?: string[];
  read_only_context?: Array<{ path: string; reason: string }>;
}

// === Dashboard Types ===

export interface DashboardTierStatus {
  name: string;
  state: TierState;
  phases?: DashboardPhaseStatus[];
}

export interface DashboardPhaseStatus {
  id: string;
  name: string;
  state: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
}

export interface DashboardRunStatus {
  run_id: string;
  state: string;
  current_tier_name?: string;
  current_phase_name?: string;
  current_tier_index?: number;
  current_phase_index?: number;
  total_tiers: number;
  total_phases: number;
  completed_tiers: number;
  completed_phases: number;
  percent_complete: number;
  tiers_percent_complete: number;
  tokens_used: number;
  token_cap: number;
  token_utilization: number;
  minor_issues_count: number;
  major_issues_count: number;
  quality_level?: string;
  quality_blocked: boolean;
  quality_warnings: string[];
  token_efficiency?: Record<string, unknown>;
  tiers?: DashboardTierStatus[];
}

// === Artifact Types (GAP-8.10.1) ===

export interface RunArtifacts {
  run_id: string;
  plan_preview?: string;
  phase_summaries: PhaseSummary[];
  logs: LogEntry[];
  completion_report?: CompletionReport;
}

export interface PhaseSummary {
  phase_id: string;
  name: string;
  state: PhaseState;
  summary?: string;
  files_changed: string[];
  lines_added: number;
  lines_removed: number;
  tokens_used: number;
  duration_minutes?: number;
}

export interface LogEntry {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  message: string;
  phase_id?: string;
}

export interface CompletionReport {
  status: 'success' | 'failed' | 'partial';
  total_phases: number;
  completed_phases: number;
  failed_phases: number;
  total_tokens_used: number;
  total_duration_minutes: number;
  issues_summary: {
    minor: number;
    major: number;
  };
}

// === Browser Artifacts (GAP-8.10.3) ===

export interface BrowserArtifact {
  id: string;
  type: 'screenshot' | 'har' | 'video' | 'trace';
  filename: string;
  path: string;
  size_bytes: number;
  created_at: string;
  phase_id?: string;
  metadata?: Record<string, unknown>;
}

// === API Response Types ===

export interface ApiError {
  detail: string;
  status_code?: number;
}

export interface RunListResponse {
  runs: RunSummary[];
  total: number;
}

export interface RunSummary {
  id: string;
  state: RunState;
  goal_anchor?: string;
  created_at: string;
  updated_at: string;
  percent_complete: number;
  tokens_used: number;
  token_cap: number;
  current_phase?: string;
  has_errors: boolean;
}
