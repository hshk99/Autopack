/**
 * Runs Inbox page component (GAP-8.10.2)
 *
 * Displays a paginated list of all runs with summary information.
 * Links to individual run views for artifacts and progress.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchRuns, RunSummary } from '../api/runs';

const PAGE_SIZE = 20;

const RunsInbox: React.FC = () => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadRuns = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchRuns(PAGE_SIZE, offset);
        setRuns(response.runs);
        setTotal(response.total);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load runs');
      } finally {
        setLoading(false);
      }
    };
    loadRuns();
  }, [offset]);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const getStateColor = (state: string): string => {
    if (state.includes('SUCCESS') || state === 'COMPLETED') return '#28a745';
    if (state.includes('FAILED') || state === 'FAILED') return '#dc3545';
    if (state === 'IN_PROGRESS' || state === 'RUNNING') return '#007bff';
    return '#6c757d';
  };

  const hasNextPage = offset + PAGE_SIZE < total;
  const hasPrevPage = offset > 0;

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>Runs Inbox</h1>
      <p style={{ color: '#666', marginBottom: '20px' }}>
        Total runs: {total}
      </p>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && !error && (
        <>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              marginBottom: '20px',
            }}
          >
            <thead>
              <tr
                style={{
                  backgroundColor: '#f8f9fa',
                  borderBottom: '2px solid #dee2e6',
                }}
              >
                <th style={{ padding: '12px', textAlign: 'left' }}>Run ID</th>
                <th style={{ padding: '12px', textAlign: 'left' }}>State</th>
                <th style={{ padding: '12px', textAlign: 'left' }}>Created</th>
                <th style={{ padding: '12px', textAlign: 'right' }}>
                  Phases
                </th>
                <th style={{ padding: '12px', textAlign: 'right' }}>
                  Tokens
                </th>
                <th style={{ padding: '12px', textAlign: 'left' }}>
                  Current Phase
                </th>
                <th style={{ padding: '12px', textAlign: 'center' }}>
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  style={{ borderBottom: '1px solid #dee2e6' }}
                >
                  <td style={{ padding: '12px' }}>
                    <code>{run.id}</code>
                  </td>
                  <td style={{ padding: '12px' }}>
                    <span
                      style={{
                        color: getStateColor(run.state),
                        fontWeight: 'bold',
                      }}
                    >
                      {run.state}
                    </span>
                  </td>
                  <td style={{ padding: '12px' }}>
                    {formatDate(run.created_at)}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'right' }}>
                    {run.phases_completed}/{run.phases_total}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'right' }}>
                    {run.tokens_used.toLocaleString()}
                    {run.token_cap && (
                      <span style={{ color: '#666' }}>
                        /{run.token_cap.toLocaleString()}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '12px', color: '#666' }}>
                    {run.current_phase_name || '-'}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'center' }}>
                    <Link
                      to={`/runs/${run.id}/progress`}
                      style={{ marginRight: '10px' }}
                    >
                      Progress
                    </Link>
                    <Link
                      to={`/runs/${run.id}/artifacts`}
                      style={{ marginRight: '10px' }}
                    >
                      Artifacts
                    </Link>
                    <Link to={`/runs/${run.id}/browser`}>Browser</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <button
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={!hasPrevPage}
              style={{
                padding: '8px 16px',
                cursor: hasPrevPage ? 'pointer' : 'not-allowed',
              }}
            >
              Previous
            </button>
            <span>
              Showing {offset + 1}-{Math.min(offset + PAGE_SIZE, total)} of{' '}
              {total}
            </span>
            <button
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={!hasNextPage}
              style={{
                padding: '8px 16px',
                cursor: hasNextPage ? 'pointer' : 'not-allowed',
              }}
            >
              Next
            </button>
          </div>
        </>
      )}

      <div style={{ marginTop: '20px' }}>
        <Link to="/">Back to Dashboard</Link>
      </div>
    </div>
  );
};

export default RunsInbox;
