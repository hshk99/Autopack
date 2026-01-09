/**
 * Run Artifacts page component (GAP-8.10.1)
 *
 * Displays file artifacts for a specific run with download links.
 */
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  fetchArtifactsIndex,
  getArtifactFileUrl,
  ArtifactInfo,
} from '../api/runs';

const RunArtifacts: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([]);
  const [totalSize, setTotalSize] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;

    const loadArtifacts = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchArtifactsIndex(runId);
        setArtifacts(response.artifacts);
        setTotalSize(response.total_size_bytes);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load artifacts');
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

  const getFileIcon = (path: string): string => {
    const ext = path.split('.').pop()?.toLowerCase() || '';
    const icons: Record<string, string> = {
      md: 'markdown',
      json: 'json',
      txt: 'text',
      log: 'log',
      png: 'image',
      jpg: 'image',
      jpeg: 'image',
      webm: 'video',
      har: 'network',
    };
    return icons[ext] || 'file';
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>Run Artifacts</h1>
      <p style={{ color: '#666', marginBottom: '10px' }}>
        Run ID: <code>{runId}</code>
      </p>
      <p style={{ color: '#666', marginBottom: '20px' }}>
        Total size: {formatSize(totalSize)} | Files: {artifacts.length}
      </p>

      {loading && <p>Loading artifacts...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && !error && artifacts.length === 0 && (
        <p>No artifacts found for this run.</p>
      )}

      {!loading && !error && artifacts.length > 0 && (
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
              <th style={{ padding: '12px', textAlign: 'left' }}>File</th>
              <th style={{ padding: '12px', textAlign: 'right' }}>Size</th>
              <th style={{ padding: '12px', textAlign: 'left' }}>Modified</th>
              <th style={{ padding: '12px', textAlign: 'center' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {artifacts.map((artifact) => (
              <tr
                key={artifact.path}
                style={{ borderBottom: '1px solid #dee2e6' }}
              >
                <td style={{ padding: '12px' }}>
                  <span style={{ marginRight: '8px', color: '#666' }}>
                    [{getFileIcon(artifact.path)}]
                  </span>
                  <code>{artifact.path}</code>
                </td>
                <td
                  style={{ padding: '12px', textAlign: 'right', color: '#666' }}
                >
                  {formatSize(artifact.size_bytes)}
                </td>
                <td style={{ padding: '12px', color: '#666' }}>
                  {formatDate(artifact.modified_at)}
                </td>
                <td style={{ padding: '12px', textAlign: 'center' }}>
                  <a
                    href={getArtifactFileUrl(runId!, artifact.path)}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#007bff', textDecoration: 'none' }}
                  >
                    View
                  </a>
                  {' | '}
                  <a
                    href={getArtifactFileUrl(runId!, artifact.path)}
                    download
                    style={{ color: '#007bff', textDecoration: 'none' }}
                  >
                    Download
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: '20px' }}>
        <Link to={`/runs/${runId}/progress`} style={{ marginRight: '15px' }}>
          View Progress
        </Link>
        <Link to={`/runs/${runId}/browser`} style={{ marginRight: '15px' }}>
          Browser Artifacts
        </Link>
        <Link to="/runs">Back to Runs Inbox</Link>
      </div>
    </div>
  );
};

export default RunArtifacts;
