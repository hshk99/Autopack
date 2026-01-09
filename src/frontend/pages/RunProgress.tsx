/**
 * Run Progress page component (GAP-8.10.4)
 *
 * Displays phase-by-phase progress for a specific run.
 */
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchRunProgress, RunProgressResponse, PhaseProgressInfo } from '../api/runs';

const RunProgress: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [progress, setProgress] = useState<RunProgressResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;

    const loadProgress = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchRunProgress(runId);
        setProgress(response);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load progress');
      } finally {
        setLoading(false);
      }
    };
    loadProgress();
  }, [runId]);

  const formatDuration = (seconds: number | null): string => {
    if (seconds === null) return '-';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
  };

  const getStateColor = (state: string): string => {
    if (state === 'COMPLETED') return '#28a745';
    if (state === 'FAILED' || state.includes('FAILED')) return '#dc3545';
    if (state === 'IN_PROGRESS') return '#007bff';
    if (state === 'QUEUED' || state === 'PENDING') return '#ffc107';
    if (state === 'SKIPPED') return '#6c757d';
    return '#6c757d';
  };

  const getStateIcon = (state: string): string => {
    if (state === 'COMPLETED') return 'v';
    if (state === 'FAILED' || state.includes('FAILED')) return 'x';
    if (state === 'IN_PROGRESS') return '~';
    if (state === 'QUEUED' || state === 'PENDING') return 'o';
    if (state === 'SKIPPED') return '-';
    return '?';
  };

  // Group phases by tier
  const phasesByTier = progress?.phases.reduce<Record<string, PhaseProgressInfo[]>>(
    (acc, phase) => {
      const tierId = phase.tier_id;
      if (!acc[tierId]) {
        acc[tierId] = [];
      }
      acc[tierId].push(phase);
      return acc;
    },
    {}
  ) || {};

  const completionPercent = progress
    ? Math.round((progress.phases_completed / progress.phases_total) * 100)
    : 0;

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>Run Progress</h1>
      <p style={{ color: '#666', marginBottom: '20px' }}>
        Run ID: <code>{runId}</code>
      </p>

      {loading && <p>Loading progress...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && !error && progress && (
        <>
          {/* Summary Cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '15px',
              marginBottom: '30px',
            }}
          >
            <div
              style={{
                padding: '20px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666' }}>State</div>
              <div
                style={{
                  fontSize: '24px',
                  fontWeight: 'bold',
                  color: getStateColor(progress.state),
                }}
              >
                {progress.state}
              </div>
            </div>
            <div
              style={{
                padding: '20px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666' }}>Progress</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
                {progress.phases_completed}/{progress.phases_total}
              </div>
              <div style={{ fontSize: '14px', color: '#666' }}>
                ({completionPercent}%)
              </div>
            </div>
            <div
              style={{
                padding: '20px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666' }}>Tokens Used</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
                {progress.tokens_used.toLocaleString()}
              </div>
              {progress.token_cap && (
                <div style={{ fontSize: '14px', color: '#666' }}>
                  / {progress.token_cap.toLocaleString()}
                </div>
              )}
            </div>
            <div
              style={{
                padding: '20px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666' }}>Duration</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
                {formatDuration(progress.elapsed_seconds)}
              </div>
            </div>
          </div>

          {/* Progress Bar */}
          <div style={{ marginBottom: '30px' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: '5px',
              }}
            >
              <span>Overall Progress</span>
              <span>
                {progress.phases_completed} completed, {progress.phases_in_progress}{' '}
                in progress, {progress.phases_pending} pending
              </span>
            </div>
            <div
              style={{
                height: '20px',
                backgroundColor: '#e9ecef',
                borderRadius: '4px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${completionPercent}%`,
                  backgroundColor: '#28a745',
                  transition: 'width 0.3s',
                }}
              />
            </div>
          </div>

          {/* Phases by Tier */}
          {Object.entries(phasesByTier).map(([tierId, tierPhases]) => (
            <div
              key={tierId}
              style={{
                marginBottom: '25px',
                border: '1px solid #dee2e6',
                borderRadius: '8px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  backgroundColor: '#f8f9fa',
                  padding: '12px 16px',
                  borderBottom: '1px solid #dee2e6',
                  fontWeight: 'bold',
                }}
              >
                Tier: {tierId}
              </div>
              <div style={{ padding: '10px' }}>
                {tierPhases.map((phase) => (
                  <div
                    key={phase.phase_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '8px 12px',
                      borderBottom: '1px solid #f0f0f0',
                    }}
                  >
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: '24px',
                        height: '24px',
                        borderRadius: '50%',
                        backgroundColor: getStateColor(phase.state),
                        color: 'white',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        marginRight: '12px',
                      }}
                    >
                      {getStateIcon(phase.state)}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 500 }}>
                        <code style={{ marginRight: '8px' }}>
                          {phase.phase_id}
                        </code>
                        {phase.name}
                      </div>
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        Index: {phase.phase_index}
                        {phase.tokens_used !== null && (
                          <span style={{ marginLeft: '15px' }}>
                            Tokens: {phase.tokens_used.toLocaleString()}
                          </span>
                        )}
                        {phase.builder_attempts !== null && (
                          <span style={{ marginLeft: '15px' }}>
                            Attempts: {phase.builder_attempts}
                          </span>
                        )}
                      </div>
                    </div>
                    <span
                      style={{
                        padding: '4px 8px',
                        borderRadius: '4px',
                        fontSize: '12px',
                        backgroundColor: getStateColor(phase.state),
                        color: 'white',
                      }}
                    >
                      {phase.state}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </>
      )}

      <div style={{ marginTop: '20px' }}>
        <Link to={`/runs/${runId}/artifacts`} style={{ marginRight: '15px' }}>
          View Artifacts
        </Link>
        <Link to={`/runs/${runId}/browser`} style={{ marginRight: '15px' }}>
          Browser Artifacts
        </Link>
        <Link to="/runs">Back to Runs Inbox</Link>
      </div>
    </div>
  );
};

export default RunProgress;
