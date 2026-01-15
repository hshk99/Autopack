/**
 * Run Artifacts page component (GAP-8.10.1)
 *
 * Displays artifact files for a run with file browser and content viewer.
 * Shows badges for truncated or redacted artifacts.
 */
import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  fetchArtifactsIndex,
  fetchArtifactFile,
  ArtifactFileResponse,
  Artifact,
} from '../api/runs';

interface ArtifactMetadata {
  truncated: boolean;
  redacted: boolean;
}

const RunArtifacts: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [totalSize, setTotalSize] = useState(0);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileMetadata, setFileMetadata] = useState<ArtifactMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadArtifacts = async () => {
      if (!runId) return;
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

  const handleFileClick = async (path: string) => {
    if (!runId) return;
    setSelectedFile(path);
    setFileMetadata(null);
    try {
      const response = await fetchArtifactFile(runId, path);
      setFileContent(response.content);
      setFileMetadata({
        truncated: response.truncated,
        redacted: response.redacted,
      });
    } catch (e) {
      setFileContent(
        `Error loading file: ${e instanceof Error ? e.message : 'Unknown error'}`
      );
      setFileMetadata(null);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const Badge: React.FC<{ label: string; color: string }> = ({
    label,
    color,
  }) => (
    <span
      style={{
        display: 'inline-block',
        padding: '4px 8px',
        marginRight: '8px',
        marginBottom: '12px',
        backgroundColor: color,
        color: '#fff',
        borderRadius: '4px',
        fontSize: '12px',
        fontWeight: 500,
      }}
    >
      {label}
    </span>
  );

  return (
    <div style={{ padding: '20px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1>Artifacts: {runId}</h1>
      <p style={{ color: '#666', marginBottom: '20px' }}>
        Total size: {formatSize(totalSize)} | Files: {artifacts.length}
      </p>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && !error && (
        <div style={{ display: 'flex', gap: '20px' }}>
          {/* File list */}
          <div
            style={{
              width: '300px',
              borderRight: '1px solid #dee2e6',
              paddingRight: '20px',
              maxHeight: '600px',
              overflowY: 'auto',
            }}
          >
            <h3>Files</h3>
            {artifacts.length === 0 ? (
              <p style={{ color: '#666' }}>No artifacts found</p>
            ) : (
              <ul style={{ listStyle: 'none', padding: 0 }}>
                {artifacts.map((artifact) => (
                  <li
                    key={artifact.path}
                    style={{
                      padding: '8px',
                      cursor: 'pointer',
                      backgroundColor:
                        selectedFile === artifact.path ? '#e9ecef' : 'transparent',
                      borderRadius: '4px',
                      marginBottom: '4px',
                    }}
                    onClick={() => handleFileClick(artifact.path)}
                  >
                    <div style={{ fontWeight: 500 }}>{artifact.path}</div>
                    <div style={{ fontSize: '12px', color: '#666' }}>
                      {formatSize(artifact.size_bytes)} |{' '}
                      {formatDate(artifact.modified_at)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* File content */}
          <div style={{ flex: 1 }}>
            <h3>Content: {selectedFile || 'Select a file'}</h3>
            {selectedFile && fileContent !== null ? (
              <>
                {fileMetadata && (fileMetadata.truncated || fileMetadata.redacted) && (
                  <div style={{ marginBottom: '12px' }}>
                    {fileMetadata.truncated && (
                      <Badge
                        label="⚠️ Truncated"
                        color="#ff9800"
                      />
                    )}
                    {fileMetadata.redacted && (
                      <Badge
                        label="🔒 Redacted"
                        color="#f44336"
                      />
                    )}
                  </div>
                )}
                <pre
                  style={{
                    backgroundColor: '#f8f9fa',
                    padding: '16px',
                    borderRadius: '4px',
                    overflow: 'auto',
                    maxHeight: '500px',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {fileContent}
                </pre>
              </>
            ) : (
              <p style={{ color: '#666' }}>
                Click on a file to view its content
              </p>
            )}
          </div>
        </div>
      )}

      <div style={{ marginTop: '20px' }}>
        <Link to="/runs" style={{ marginRight: '15px' }}>
          Back to Runs
        </Link>
        <Link to={`/runs/${runId}/progress`} style={{ marginRight: '15px' }}>
          Progress
        </Link>
        <Link to={`/runs/${runId}/browser`}>Browser Artifacts</Link>
      </div>
    </div>
  );
};

export default RunArtifacts;
