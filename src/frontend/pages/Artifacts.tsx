/**
 * Artifacts panel page - displays run artifacts
 *
 * GAP-8.10.1 implementation
 * Surface: plan preview, phase summaries, logs, completion report
 */
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { ProgressBar } from '../components/ProgressBar';
import { getRun, getRunStatus, getRunErrors } from '../services/api';
import type { Run, DashboardRunStatus, Phase } from '../types';

type Tab = 'overview' | 'phases' | 'logs' | 'errors';

const Artifacts: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [status, setStatus] = useState<DashboardRunStatus | null>(null);
  const [errors, setErrors] = useState<{ error_count: number; errors: unknown[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('overview');

  useEffect(() => {
    if (!runId) return;

    const loadData = async () => {
      setLoading(true);
      setError(null);

      try {
        const [runData, statusData] = await Promise.all([
          getRun(runId),
          getRunStatus(runId).catch(() => null),
        ]);
        setRun(runData);
        setStatus(statusData);

        // Load errors separately (may fail if no errors)
        try {
          const errorsData = await getRunErrors(runId);
          setErrors(errorsData);
        } catch {
          setErrors(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load run data');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [runId]);

  if (loading) {
    return (
      <div style={{ padding: 'var(--spacing-lg)', textAlign: 'center' }}>
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 'var(--spacing-lg)' }}>
        <div
          style={{
            padding: 'var(--spacing-md)',
            backgroundColor: '#fef2f2',
            border: '1px solid var(--color-error)',
            borderRadius: '0.5rem',
          }}
        >
          <h2 style={{ color: 'var(--color-error)', margin: 0 }}>Error</h2>
          <p>{error}</p>
          <Link to="/" style={{ color: 'var(--color-primary)' }}>
            ← Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div style={{ padding: 'var(--spacing-lg)' }}>
        <p>Run not found</p>
        <Link to="/" style={{ color: 'var(--color-primary)' }}>
          ← Back to Dashboard
        </Link>
      </div>
    );
  }

  const allPhases: Phase[] =
    run.tiers?.flatMap((tier) => tier.phases || []).sort((a, b) => a.phase_index - b.phase_index) ||
    [];

  return (
    <div style={{ padding: 'var(--spacing-lg)', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--spacing-lg)' }}>
        <Link
          to="/"
          style={{
            color: 'var(--color-text-secondary)',
            textDecoration: 'none',
            fontSize: '0.875rem',
          }}
        >
          ← Back to Dashboard
        </Link>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 'var(--spacing-sm)',
          }}
        >
          <h1 style={{ margin: 0 }}>{run.id}</h1>
          <StatusBadge status={run.state} size="lg" />
        </div>
        {run.goal_anchor && (
          <p style={{ color: 'var(--color-text-secondary)', marginTop: 'var(--spacing-xs)' }}>
            {run.goal_anchor}
          </p>
        )}
      </div>

      {/* Progress overview */}
      {status && (
        <div
          style={{
            padding: 'var(--spacing-md)',
            backgroundColor: 'var(--color-bg-secondary)',
            borderRadius: '0.5rem',
            marginBottom: 'var(--spacing-lg)',
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--spacing-md)' }}>
            <div>
              <ProgressBar
                percent={status.percent_complete}
                label="Overall Progress"
                color={run.state.startsWith('DONE_FAILED') ? 'error' : 'primary'}
              />
            </div>
            <div>
              <ProgressBar
                percent={status.token_utilization * 100}
                label="Token Budget"
                color={status.token_utilization > 0.9 ? 'warning' : 'primary'}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                Phases: {status.completed_phases} / {status.total_phases}
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                Tiers: {status.completed_tiers} / {status.total_tiers}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div
        style={{
          display: 'flex',
          gap: 'var(--spacing-sm)',
          borderBottom: '1px solid var(--color-border)',
          marginBottom: 'var(--spacing-md)',
        }}
      >
        {(['overview', 'phases', 'logs', 'errors'] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: 'var(--spacing-sm) var(--spacing-md)',
              border: 'none',
              backgroundColor: 'transparent',
              cursor: 'pointer',
              borderBottom: activeTab === tab ? '2px solid var(--color-primary)' : '2px solid transparent',
              color: activeTab === tab ? 'var(--color-primary)' : 'var(--color-text-secondary)',
              fontWeight: activeTab === tab ? 600 : 400,
              textTransform: 'capitalize',
            }}
          >
            {tab}
            {tab === 'errors' && errors && errors.error_count > 0 && (
              <span
                style={{
                  marginLeft: '0.5rem',
                  padding: '0.125rem 0.375rem',
                  backgroundColor: 'var(--color-error)',
                  color: '#fff',
                  borderRadius: '999px',
                  fontSize: '0.75rem',
                }}
              >
                {errors.error_count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div>
          <h2>Run Overview</h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: 'var(--spacing-md)',
            }}
          >
            <InfoCard label="Run ID" value={run.id} />
            <InfoCard label="State" value={run.state} />
            <InfoCard label="Safety Profile" value={run.safety_profile} />
            <InfoCard label="Run Scope" value={run.run_scope} />
            <InfoCard label="Tokens Used" value={`${run.tokens_used.toLocaleString()} / ${run.token_cap.toLocaleString()}`} />
            <InfoCard label="Issues" value={`Minor: ${run.minor_issues_count}, Major: ${run.major_issues_count}`} />
            <InfoCard label="Created" value={new Date(run.created_at).toLocaleString()} />
            <InfoCard label="Updated" value={new Date(run.updated_at).toLocaleString()} />
          </div>
          {run.failure_reason && (
            <div
              style={{
                marginTop: 'var(--spacing-md)',
                padding: 'var(--spacing-md)',
                backgroundColor: '#fef2f2',
                border: '1px solid var(--color-error)',
                borderRadius: '0.5rem',
              }}
            >
              <strong>Failure Reason:</strong>
              <p style={{ margin: 'var(--spacing-xs) 0 0' }}>{run.failure_reason}</p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'phases' && (
        <div>
          <h2>Phases ({allPhases.length})</h2>
          {allPhases.length === 0 ? (
            <p style={{ color: 'var(--color-text-secondary)' }}>No phases yet</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
              {allPhases.map((phase) => (
                <PhaseCard key={phase.id} phase={phase} />
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'logs' && (
        <div>
          <h2>Logs</h2>
          <p style={{ color: 'var(--color-text-secondary)' }}>
            Log viewer coming soon. For now, check the run directory:
          </p>
          <code
            style={{
              display: 'block',
              padding: 'var(--spacing-md)',
              backgroundColor: 'var(--color-bg-secondary)',
              borderRadius: '0.5rem',
              fontFamily: 'var(--font-mono)',
              overflow: 'auto',
            }}
          >
            .autonomous_runs/autopack/runs/{run.id}/run.log
          </code>
        </div>
      )}

      {activeTab === 'errors' && (
        <div>
          <h2>Errors</h2>
          {!errors || errors.error_count === 0 ? (
            <p style={{ color: 'var(--color-success)' }}>No errors recorded</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
              {errors.errors.map((err, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: 'var(--spacing-md)',
                    backgroundColor: '#fef2f2',
                    border: '1px solid var(--color-error)',
                    borderRadius: '0.5rem',
                  }}
                >
                  <pre
                    style={{
                      margin: 0,
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.875rem',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {JSON.stringify(err, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Helper components

const InfoCard: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div
    style={{
      padding: 'var(--spacing-sm)',
      backgroundColor: 'var(--color-bg-secondary)',
      borderRadius: '0.25rem',
    }}
  >
    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>{label}</div>
    <div style={{ fontWeight: 500 }}>{value}</div>
  </div>
);

const PhaseCard: React.FC<{ phase: Phase }> = ({ phase }) => (
  <div
    style={{
      padding: 'var(--spacing-md)',
      border: '1px solid var(--color-border)',
      borderRadius: '0.5rem',
    }}
  >
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <div>
        <div style={{ fontWeight: 600 }}>
          {phase.phase_index + 1}. {phase.name || phase.phase_id}
        </div>
        {phase.description && (
          <div style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
            {phase.description}
          </div>
        )}
      </div>
      <StatusBadge status={phase.state} size="sm" />
    </div>
    <div
      style={{
        marginTop: 'var(--spacing-sm)',
        display: 'flex',
        gap: 'var(--spacing-md)',
        fontSize: '0.75rem',
        color: 'var(--color-text-secondary)',
      }}
    >
      <span>Tokens: {phase.tokens_used.toLocaleString()}</span>
      <span>Builder: {phase.builder_attempts} attempts</span>
      <span>Auditor: {phase.auditor_attempts} attempts</span>
      {phase.task_category && <span>Category: {phase.task_category}</span>}
    </div>
    {phase.last_failure_reason && (
      <div
        style={{
          marginTop: 'var(--spacing-sm)',
          padding: 'var(--spacing-xs)',
          backgroundColor: '#fef2f2',
          borderRadius: '0.25rem',
          fontSize: '0.75rem',
          color: 'var(--color-error)',
        }}
      >
        {phase.last_failure_reason}
      </div>
    )}
  </div>
);

export default Artifacts;
