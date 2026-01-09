/**
 * Run Browser Artifacts page component (GAP-8.10.3)
 *
 * Displays browser-specific artifacts (screenshots, HTML) for a run.
 */
import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { fetchBrowserArtifacts, BrowserArtifact } from '../api/runs';

const RunBrowserArtifacts: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [artifacts, setArtifacts] = useState<BrowserArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadArtifacts = async () => {
      if (!runId) return;
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
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const screenshots = artifacts.filter((a) => a.type === 'screenshot');
  const htmlFiles = artifacts.filter((a) => a.type === 'html');

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>Browser Artifacts: {runId}</h1>
      <p style={{ color: '#666', marginBottom: '20px' }}>
        Screenshots: {screenshots.length} | HTML: {htmlFiles.length}
      </p>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && !error && (
        <>
          {artifacts.length === 0 ? (
            <p style={{ color: '#666' }}>No browser artifacts found</p>
          ) : (
            <>
              {/* Screenshots section */}
              {screenshots.length > 0 && (
                <section style={{ marginBottom: '30px' }}>
                  <h2>Screenshots</h2>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                      gap: '20px',
                    }}
                  >
                    {screenshots.map((artifact) => (
                      <div
                        key={artifact.path}
                        style={{
                          border: '1px solid #dee2e6',
                          borderRadius: '8px',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            height: '200px',
                            backgroundColor: '#f8f9fa',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          <img
                            src={`/api/runs/${runId}/artifacts/file?path=${encodeURIComponent(artifact.path)}`}
                            alt={artifact.path}
                            style={{
                              maxWidth: '100%',
                              maxHeight: '100%',
                              objectFit: 'contain',
                            }}
                          />
                        </div>
                        <div style={{ padding: '12px' }}>
                          <div
                            style={{
                              fontWeight: 500,
                              marginBottom: '4px',
                              wordBreak: 'break-word',
                            }}
                          >
                            {artifact.path}
                          </div>
                          <div style={{ fontSize: '12px', color: '#666' }}>
                            {formatSize(artifact.size_bytes)} |{' '}
                            {formatDate(artifact.modified_at)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* HTML files section */}
              {htmlFiles.length > 0 && (
                <section>
                  <h2>HTML Files</h2>
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
                        <th style={{ padding: '12px', textAlign: 'left' }}>
                          File
                        </th>
                        <th style={{ padding: '12px', textAlign: 'right' }}>
                          Size
                        </th>
                        <th style={{ padding: '12px', textAlign: 'left' }}>
                          Modified
                        </th>
                        <th style={{ padding: '12px', textAlign: 'center' }}>
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {htmlFiles.map((artifact) => (
                        <tr
                          key={artifact.path}
                          style={{ borderBottom: '1px solid #dee2e6' }}
                        >
                          <td style={{ padding: '12px' }}>{artifact.path}</td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            {formatSize(artifact.size_bytes)}
                          </td>
                          <td style={{ padding: '12px' }}>
                            {formatDate(artifact.modified_at)}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'center' }}>
                            <a
                              href={`/api/runs/${runId}/artifacts/file?path=${encodeURIComponent(artifact.path)}`}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              View
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )}
            </>
          )}
        </>
      )}

      <div style={{ marginTop: '20px' }}>
        <Link to="/runs" style={{ marginRight: '15px' }}>
          Back to Runs
        </Link>
        <Link to={`/runs/${runId}/artifacts`} style={{ marginRight: '15px' }}>
          All Artifacts
        </Link>
        <Link to={`/runs/${runId}/progress`}>Progress</Link>
      </div>
    </div>
  );
};

export default RunBrowserArtifacts;
