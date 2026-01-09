/**
 * Multi-run inbox view - lists active runs with status
 *
 * GAP-8.10.2 implementation
 * Shows: status, current phase, last heartbeat, links to artifacts/errors
 *
 * Note: Backend /runs endpoint needed for full functionality.
 * Currently displays placeholder until endpoint is implemented.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RunCard } from '../components/RunCard';
import type { RunSummary, RunState } from '../types';

// Placeholder data for demo - will be replaced by API call
const DEMO_RUNS: RunSummary[] = [
  {
    id: 'telemetry-v8-budget-validation',
    state: 'PHASE_EXECUTION' as RunState,
    goal_anchor: 'Validate budget floor override behavior',
    created_at: new Date(Date.now() - 3600000).toISOString(),
    updated_at: new Date(Date.now() - 60000).toISOString(),
    percent_complete: 45,
    tokens_used: 125000,
    token_cap: 500000,
    current_phase: 'T2.auth-endpoint-wiring',
    has_errors: false,
  },
  {
    id: 'fileorg-country-expansion',
    state: 'DONE_SUCCESS' as RunState,
    goal_anchor: 'Add UK and Australia document classifiers',
    created_at: new Date(Date.now() - 86400000).toISOString(),
    updated_at: new Date(Date.now() - 7200000).toISOString(),
    percent_complete: 100,
    tokens_used: 320000,
    token_cap: 500000,
    current_phase: undefined,
    has_errors: false,
  },
  {
    id: 'research-system-integration',
    state: 'DONE_FAILED_REQUIRES_HUMAN_REVIEW' as RunState,
    goal_anchor: 'Integrate research gatherers with knowledge base',
    created_at: new Date(Date.now() - 172800000).toISOString(),
    updated_at: new Date(Date.now() - 86400000).toISOString(),
    percent_complete: 67,
    tokens_used: 450000,
    token_cap: 500000,
    current_phase: 'T3.research-wiring',
    has_errors: true,
  },
];

type FilterState = 'all' | 'active' | 'completed' | 'failed';

const RunsInbox: React.FC = () => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterState>('all');
  const [apiAvailable, setApiAvailable] = useState(false);

  useEffect(() => {
    // Try to load from API, fall back to demo data
    const loadRuns = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/runs');
        if (response.ok) {
          const data = await response.json();
          setRuns(data.runs || data);
          setApiAvailable(true);
        } else {
          // API not available, use demo data
          setRuns(DEMO_RUNS);
          setApiAvailable(false);
        }
      } catch {
        // Network error, use demo data
        setRuns(DEMO_RUNS);
        setApiAvailable(false);
      } finally {
        setLoading(false);
      }
    };

    loadRuns();
  }, []);

  const filteredRuns = runs.filter((run) => {
    switch (filter) {
      case 'active':
        return !run.state.startsWith('DONE_');
      case 'completed':
        return run.state === 'DONE_SUCCESS';
      case 'failed':
        return run.state.startsWith('DONE_FAILED');
      default:
        return true;
    }
  });

  const counts = {
    all: runs.length,
    active: runs.filter((r) => !r.state.startsWith('DONE_')).length,
    completed: runs.filter((r) => r.state === 'DONE_SUCCESS').length,
    failed: runs.filter((r) => r.state.startsWith('DONE_FAILED')).length,
  };

  return (
    <div style={{ padding: 'var(--spacing-lg)', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--spacing-lg)',
        }}
      >
        <div>
          <h1 style={{ margin: 0 }}>Runs Inbox</h1>
          <p style={{ color: 'var(--color-text-secondary)', margin: 'var(--spacing-xs) 0 0' }}>
            {runs.length} total runs
          </p>
        </div>
        <Link
          to="/"
          style={{
            padding: 'var(--spacing-sm) var(--spacing-md)',
            backgroundColor: 'var(--color-primary)',
            color: '#fff',
            textDecoration: 'none',
            borderRadius: '0.25rem',
          }}
        >
          ← Dashboard
        </Link>
      </div>

      {/* API Notice */}
      {!apiAvailable && !loading && (
        <div
          style={{
            padding: 'var(--spacing-md)',
            backgroundColor: '#fffbeb',
            border: '1px solid var(--color-warning)',
            borderRadius: '0.5rem',
            marginBottom: 'var(--spacing-lg)',
          }}
        >
          <strong>Demo Mode:</strong> Showing sample data. The <code>/api/runs</code> endpoint is
          not yet implemented. Add a list runs endpoint to enable live data.
        </div>
      )}

      {/* Filters */}
      <div
        style={{
          display: 'flex',
          gap: 'var(--spacing-sm)',
          marginBottom: 'var(--spacing-md)',
          flexWrap: 'wrap',
        }}
      >
        {(['all', 'active', 'completed', 'failed'] as FilterState[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: 'var(--spacing-sm) var(--spacing-md)',
              border: filter === f ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
              backgroundColor: filter === f ? 'var(--color-primary)' : 'var(--color-bg)',
              color: filter === f ? '#fff' : 'var(--color-text)',
              borderRadius: '0.25rem',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {f} ({counts[f]})
          </button>
        ))}
      </div>

      {/* Runs List */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 'var(--spacing-xl)' }}>
          <p>Loading runs...</p>
        </div>
      ) : filteredRuns.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: 'var(--spacing-xl)',
            color: 'var(--color-text-secondary)',
          }}
        >
          <p>No runs match the current filter</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
          {filteredRuns.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}
    </div>
  );
};

export default RunsInbox;
