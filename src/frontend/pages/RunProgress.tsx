/**
 * Run Progress page component (GAP-8.10.4)
 *
 * Displays detailed phase-by-phase progress for a run.
 */
import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { fetchRunProgress, RunProgress as RunProgressData } from '../api/runs';

const RunProgress: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [progress, setProgress] = useState<RunProgressData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadProgress = async () => {
      if (!runId) return;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchRunProgress(runId);
        setProgress(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load progress');
      } finally {
        setLoading(false);
      }
    };
    loadProgress();
  }, [runId]);

  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
  };

  const getStateColor = (state: string): string => {
    switch (state) {
      case 'COMPLETE':
        return '#28a745';
      case 'EXECUTING':
        return '#007bff';
      case 'FAILED':
        return '#dc3545';
      case 'QUEUED':
        return '#6c757d';
      default:
        return '#6c757d';
    }
  };

  const getProgressPercent = (): number => {
    if (!progress || progress.phases_total === 0) return 0;
    return Math.round((progress.phases_completed / progress.phases_total) * 100);
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1>Progress: {runId}</h1>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && !error && progress && (
        <>
          {/* Summary cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '15px',
              marginBottom: '30px',
            }}
          >
            <div
              style={{
                padding: '20px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666' }}>State</div>
              <div
                style={{
                  fontSize: '20px',
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
              }}
            >
              <div style={{ fontSize: '14px', color: '#666' }}>Progress</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold' }}>
                {progress.phases_completed}/{progress.phases_total} (
                {getProgressPercent()}%)
              </div>
            </div>
            <div
              style={{
                padding: '20px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666' }}>Duration</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold' }}>
                {progress.elapsed_seconds !== null
                  ? formatDuration(progress.elapsed_seconds)
                  : '-'}
              </div>
            </div>
            <div
              style={{
                padding: '20px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666' }}>Tokens</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold' }}>
                {progress.tokens_used.toLocaleString()}
                {progress.token_cap && (
                  <span style={{ fontSize: '14px', color: '#666' }}>
                    /{progress.token_cap.toLocaleString()}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div
            style={{
              marginBottom: '30px',
              backgroundColor: '#e9ecef',
              borderRadius: '4px',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${getProgressPercent()}%`,
                height: '10px',
                backgroundColor: '#28a745',
                transition: 'width 0.3s ease',
              }}
            />
          </div>

          {/* Phase counts */}
          <div
            style={{
              display: 'flex',
              gap: '20px',
              marginBottom: '30px',
              color: '#666',
            }}
          >
            <span>Completed: {progress.phases_completed}</span>
            <span>In Progress: {progress.phases_in_progress}</span>
            <span>Pending: {progress.phases_pending}</span>
          </div>

          {/* Phases table */}
          <h2>Phases</h2>
          {progress.phases.length === 0 ? (
            <p style={{ color: '#666' }}>No phases found</p>
          ) : (
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
              }}
            >
              <thead>
                <tr
                  style={{
                    backgroundColor: '#f8f9fa',
                    borderBottom: '2px solid #dee2e6',
                  }}
                >
                  <th style={{ padding: '12px', textAlign: 'left' }}>#</th>
                  <th style={{ padding: '12px', textAlign: 'left' }}>
                    Phase ID
                  </th>
                  <th style={{ padding: '12px', textAlign: 'left' }}>Name</th>
                  <th style={{ padding: '12px', textAlign: 'left' }}>State</th>
                  <th style={{ padding: '12px', textAlign: 'right' }}>
                    Tokens
                  </th>
                  <th style={{ padding: '12px', textAlign: 'right' }}>
                    Attempts
                  </th>
                </tr>
              </thead>
              <tbody>
                {progress.phases.map((phase) => (
                  <tr
                    key={phase.phase_id}
                    style={{ borderBottom: '1px solid #dee2e6' }}
                  >
                    <td style={{ padding: '12px' }}>{phase.phase_index + 1}</td>
                    <td style={{ padding: '12px' }}>
                      <code>{phase.phase_id}</code>
                    </td>
                    <td style={{ padding: '12px' }}>{phase.name}</td>
                    <td style={{ padding: '12px' }}>
                      <span
                        style={{
                          color: getStateColor(phase.state),
                          fontWeight: 'bold',
                        }}
                      >
                        {phase.state}
                      </span>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right' }}>
                      {phase.tokens_used?.toLocaleString() || '-'}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right' }}>
                      {phase.builder_attempts || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <div style={{ marginTop: '20px' }}>
        <Link to="/runs" style={{ marginRight: '15px' }}>
          Back to Runs
        </Link>
        <Link to={`/runs/${runId}/artifacts`} style={{ marginRight: '15px' }}>
          Artifacts
        </Link>
        <Link to={`/runs/${runId}/browser`}>Browser Artifacts</Link>
      </div>
    </div>
  );
};

export default RunProgress;
