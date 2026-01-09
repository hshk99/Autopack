/**
 * Run Browser Artifacts page component (GAP-8.10.3)
 *
 * Displays browser automation artifacts (screenshots, videos, HAR logs)
 * for a specific run.
 */
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchBrowserArtifacts, BrowserArtifact } from '../api/runs';

const RunBrowserArtifacts: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [artifacts, setArtifacts] = useState<BrowserArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;

    const loadArtifacts = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchBrowserArtifacts(runId);
        setArtifacts(response.artifacts);
      } catch (e) {
        setError(
          e instanceof Error ? e.message : 'Failed to load browser artifacts'
        );
      } finally {
        setLoading(false);
      }
    };
    loadArtifacts();
  }, [runId]);

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const getClassIcon = (artifactClass: string): string => {
    const icons: Record<string, string> = {
      screenshot: 'camera',
      video: 'video',
      har_log: 'network',
      structured_data: 'json',
    };
    return icons[artifactClass] || 'file';
  };

  const getClassColor = (artifactClass: string): string => {
    const colors: Record<string, string> = {
      screenshot: '#28a745',
      video: '#007bff',
      har_log: '#ffc107',
      structured_data: '#6c757d',
    };
    return colors[artifactClass] || '#6c757d';
  };

  // Group artifacts by session
  const artifactsBySession = artifacts.reduce<Record<string, BrowserArtifact[]>>(
    (acc, artifact) => {
      const sessionId = artifact.session_id;
      if (!acc[sessionId]) {
        acc[sessionId] = [];
      }
      acc[sessionId].push(artifact);
      return acc;
    },
    {}
  );

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>Browser Artifacts</h1>
      <p style={{ color: '#666', marginBottom: '10px' }}>
        Run ID: <code>{runId}</code>
      </p>
      <p style={{ color: '#666', marginBottom: '20px' }}>
        Total artifacts: {artifacts.length} | Sessions:{' '}
        {Object.keys(artifactsBySession).length}
      </p>

      {loading && <p>Loading browser artifacts...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && !error && artifacts.length === 0 && (
        <div
          style={{
            padding: '40px',
            textAlign: 'center',
            backgroundColor: '#f8f9fa',
            borderRadius: '8px',
          }}
        >
          <p style={{ fontSize: '18px', marginBottom: '10px' }}>
            No browser artifacts found
          </p>
          <p style={{ color: '#666' }}>
            Browser artifacts are generated during automated browser sessions.
          </p>
        </div>
      )}

      {!loading && !error && artifacts.length > 0 && (
        <div>
          {Object.entries(artifactsBySession).map(([sessionId, sessionArtifacts]) => (
            <div
              key={sessionId}
              style={{
                marginBottom: '30px',
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
                }}
              >
                <strong>Session: </strong>
                <code>{sessionId}</code>
                <span style={{ color: '#666', marginLeft: '10px' }}>
                  ({sessionArtifacts.length} artifacts)
                </span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f8f9fa' }}>
                    <th style={{ padding: '10px', textAlign: 'left' }}>
                      Type
                    </th>
                    <th style={{ padding: '10px', textAlign: 'left' }}>
                      Path
                    </th>
                    <th style={{ padding: '10px', textAlign: 'right' }}>
                      Size
                    </th>
                    <th style={{ padding: '10px', textAlign: 'left' }}>
                      Created
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sessionArtifacts.map((artifact) => (
                    <tr
                      key={artifact.artifact_id}
                      style={{ borderBottom: '1px solid #dee2e6' }}
                    >
                      <td style={{ padding: '10px' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '2px 8px',
                            backgroundColor: getClassColor(artifact.artifact_class),
                            color: 'white',
                            borderRadius: '4px',
                            fontSize: '12px',
                          }}
                        >
                          [{getClassIcon(artifact.artifact_class)}]{' '}
                          {artifact.artifact_class}
                        </span>
                      </td>
                      <td style={{ padding: '10px' }}>
                        <code style={{ fontSize: '12px' }}>{artifact.path}</code>
                      </td>
                      <td
                        style={{
                          padding: '10px',
                          textAlign: 'right',
                          color: '#666',
                        }}
                      >
                        {formatSize(artifact.size_bytes)}
                      </td>
                      <td style={{ padding: '10px', color: '#666' }}>
                        {formatDate(artifact.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: '20px' }}>
        <Link to={`/runs/${runId}/progress`} style={{ marginRight: '15px' }}>
          View Progress
        </Link>
        <Link to={`/runs/${runId}/artifacts`} style={{ marginRight: '15px' }}>
          File Artifacts
        </Link>
        <Link to="/runs">Back to Runs Inbox</Link>
      </div>
    </div>
  );
};

export default RunBrowserArtifacts;
