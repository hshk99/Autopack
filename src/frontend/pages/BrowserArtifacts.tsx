/**
 * Browser/Playwright artifacts viewer
 *
 * GAP-8.10.3 implementation
 * Shows: screenshots, HAR files, video, traces associated with a run
 * Note: Does NOT implement "visual self-healing" per spec
 */
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import type { BrowserArtifact } from '../types';

type ArtifactType = 'all' | 'screenshot' | 'har' | 'video' | 'trace';

// Placeholder data for demo
const DEMO_ARTIFACTS: BrowserArtifact[] = [
  {
    id: 'ss-001',
    type: 'screenshot',
    filename: 'login-page.png',
    path: '.autonomous_runs/autopack/runs/test-run/browser/screenshots/login-page.png',
    size_bytes: 245000,
    created_at: new Date(Date.now() - 3600000).toISOString(),
    phase_id: 'T1.auth-login',
    metadata: { viewport: '1920x1080', url: 'http://localhost:3000/login' },
  },
  {
    id: 'ss-002',
    type: 'screenshot',
    filename: 'dashboard-loaded.png',
    path: '.autonomous_runs/autopack/runs/test-run/browser/screenshots/dashboard-loaded.png',
    size_bytes: 380000,
    created_at: new Date(Date.now() - 3500000).toISOString(),
    phase_id: 'T1.dashboard-verify',
    metadata: { viewport: '1920x1080', url: 'http://localhost:3000/dashboard' },
  },
  {
    id: 'har-001',
    type: 'har',
    filename: 'network-trace.har',
    path: '.autonomous_runs/autopack/runs/test-run/browser/har/network-trace.har',
    size_bytes: 125000,
    created_at: new Date(Date.now() - 3400000).toISOString(),
    phase_id: 'T1.api-calls',
    metadata: { entries: 45, duration_ms: 3200 },
  },
  {
    id: 'video-001',
    type: 'video',
    filename: 'test-recording.webm',
    path: '.autonomous_runs/autopack/runs/test-run/browser/video/test-recording.webm',
    size_bytes: 2450000,
    created_at: new Date(Date.now() - 3300000).toISOString(),
    phase_id: 'T2.e2e-test',
    metadata: { duration_seconds: 45, codec: 'VP8' },
  },
  {
    id: 'trace-001',
    type: 'trace',
    filename: 'playwright-trace.zip',
    path: '.autonomous_runs/autopack/runs/test-run/browser/traces/playwright-trace.zip',
    size_bytes: 890000,
    created_at: new Date(Date.now() - 3200000).toISOString(),
    phase_id: 'T2.e2e-test',
    metadata: { actions: 23 },
  },
];

const TYPE_ICONS: Record<string, string> = {
  screenshot: '🖼️',
  har: '📊',
  video: '🎬',
  trace: '🔍',
};

const BrowserArtifacts: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [artifacts, setArtifacts] = useState<BrowserArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<ArtifactType>('all');
  const [selectedArtifact, setSelectedArtifact] = useState<BrowserArtifact | null>(null);
  const [apiAvailable, setApiAvailable] = useState(false);

  useEffect(() => {
    if (!runId) return;

    const loadArtifacts = async () => {
      setLoading(true);
      try {
        const response = await fetch(`/api/runs/${runId}/browser-artifacts`);
        if (response.ok) {
          const data = await response.json();
          setArtifacts(data);
          setApiAvailable(true);
        } else {
          // API not available, use demo data
          setArtifacts(DEMO_ARTIFACTS);
          setApiAvailable(false);
        }
      } catch {
        // Network error, use demo data
        setArtifacts(DEMO_ARTIFACTS);
        setApiAvailable(false);
      } finally {
        setLoading(false);
      }
    };

    loadArtifacts();
  }, [runId]);

  const filteredArtifacts =
    filter === 'all' ? artifacts : artifacts.filter((a) => a.type === filter);

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const counts: Record<ArtifactType, number> = {
    all: artifacts.length,
    screenshot: artifacts.filter((a) => a.type === 'screenshot').length,
    har: artifacts.filter((a) => a.type === 'har').length,
    video: artifacts.filter((a) => a.type === 'video').length,
    trace: artifacts.filter((a) => a.type === 'trace').length,
  };

  return (
    <div style={{ padding: 'var(--spacing-lg)', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--spacing-lg)' }}>
        <Link
          to={`/builds/${runId}`}
          style={{
            color: 'var(--color-text-secondary)',
            textDecoration: 'none',
            fontSize: '0.875rem',
          }}
        >
          ← Back to Run
        </Link>
        <h1 style={{ margin: 'var(--spacing-sm) 0 0' }}>Browser Artifacts</h1>
        <p style={{ color: 'var(--color-text-secondary)' }}>
          Run: {runId} • {artifacts.length} artifacts
        </p>
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
          <strong>Demo Mode:</strong> Showing sample data. The{' '}
          <code>/api/runs/{'{runId}'}/browser-artifacts</code> endpoint is not yet implemented.
        </div>
      )}

      {/* Type Filters */}
      <div
        style={{
          display: 'flex',
          gap: 'var(--spacing-sm)',
          marginBottom: 'var(--spacing-md)',
          flexWrap: 'wrap',
        }}
      >
        {(['all', 'screenshot', 'har', 'video', 'trace'] as ArtifactType[]).map((type) => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            style={{
              padding: 'var(--spacing-sm) var(--spacing-md)',
              border: filter === type ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
              backgroundColor: filter === type ? 'var(--color-primary)' : 'var(--color-bg)',
              color: filter === type ? '#fff' : 'var(--color-text)',
              borderRadius: '0.25rem',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {type !== 'all' && TYPE_ICONS[type]} {type} ({counts[type]})
          </button>
        ))}
      </div>

      {/* Artifacts Grid */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 'var(--spacing-xl)' }}>
          <p>Loading artifacts...</p>
        </div>
      ) : filteredArtifacts.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: 'var(--spacing-xl)',
            color: 'var(--color-text-secondary)',
          }}
        >
          <p>No browser artifacts found</p>
          <p style={{ fontSize: '0.875rem' }}>
            Browser artifacts are generated during Playwright/browser-based testing phases
          </p>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 'var(--spacing-md)',
          }}
        >
          {filteredArtifacts.map((artifact) => (
            <div
              key={artifact.id}
              onClick={() => setSelectedArtifact(artifact)}
              style={{
                padding: 'var(--spacing-md)',
                border: '1px solid var(--color-border)',
                borderRadius: '0.5rem',
                backgroundColor: 'var(--color-bg)',
                cursor: 'pointer',
                transition: 'border-color 0.2s, box-shadow 0.2s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--color-primary)';
                e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--color-border)';
                e.currentTarget.style.boxShadow = 'none';
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--spacing-sm)' }}>
                <span style={{ fontSize: '1.5rem' }}>{TYPE_ICONS[artifact.type]}</span>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div
                    style={{
                      fontWeight: 600,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {artifact.filename}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                    {artifact.type} • {formatSize(artifact.size_bytes)}
                  </div>
                </div>
              </div>
              {artifact.phase_id && (
                <div
                  style={{
                    marginTop: 'var(--spacing-sm)',
                    fontSize: '0.75rem',
                    color: 'var(--color-text-secondary)',
                  }}
                >
                  Phase: {artifact.phase_id}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedArtifact && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 'var(--spacing-lg)',
            zIndex: 1000,
          }}
          onClick={() => setSelectedArtifact(null)}
        >
          <div
            style={{
              backgroundColor: 'var(--color-bg)',
              borderRadius: '0.5rem',
              padding: 'var(--spacing-lg)',
              maxWidth: '600px',
              width: '100%',
              maxHeight: '80vh',
              overflow: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
              <h2 style={{ margin: 0 }}>
                {TYPE_ICONS[selectedArtifact.type]} {selectedArtifact.filename}
              </h2>
              <button
                onClick={() => setSelectedArtifact(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '1.5rem',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                ×
              </button>
            </div>

            <div style={{ marginTop: 'var(--spacing-md)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--spacing-sm)' }}>
                <div>
                  <strong>Type:</strong> {selectedArtifact.type}
                </div>
                <div>
                  <strong>Size:</strong> {formatSize(selectedArtifact.size_bytes)}
                </div>
                <div>
                  <strong>Created:</strong>{' '}
                  {new Date(selectedArtifact.created_at).toLocaleString()}
                </div>
                {selectedArtifact.phase_id && (
                  <div>
                    <strong>Phase:</strong> {selectedArtifact.phase_id}
                  </div>
                )}
              </div>

              <div style={{ marginTop: 'var(--spacing-md)' }}>
                <strong>Path:</strong>
                <code
                  style={{
                    display: 'block',
                    padding: 'var(--spacing-sm)',
                    backgroundColor: 'var(--color-bg-secondary)',
                    borderRadius: '0.25rem',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.75rem',
                    overflow: 'auto',
                    marginTop: 'var(--spacing-xs)',
                  }}
                >
                  {selectedArtifact.path}
                </code>
              </div>

              {selectedArtifact.metadata && Object.keys(selectedArtifact.metadata).length > 0 && (
                <div style={{ marginTop: 'var(--spacing-md)' }}>
                  <strong>Metadata:</strong>
                  <pre
                    style={{
                      padding: 'var(--spacing-sm)',
                      backgroundColor: 'var(--color-bg-secondary)',
                      borderRadius: '0.25rem',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.75rem',
                      overflow: 'auto',
                      marginTop: 'var(--spacing-xs)',
                    }}
                  >
                    {JSON.stringify(selectedArtifact.metadata, null, 2)}
                  </pre>
                </div>
              )}

              <div style={{ marginTop: 'var(--spacing-lg)', display: 'flex', gap: 'var(--spacing-sm)' }}>
                <button
                  style={{
                    padding: 'var(--spacing-sm) var(--spacing-md)',
                    backgroundColor: 'var(--color-primary)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '0.25rem',
                    cursor: 'pointer',
                  }}
                  onClick={() => {
                    // Would open file in viewer or download
                    alert(`Download: ${selectedArtifact.path}`);
                  }}
                >
                  Download
                </button>
                {selectedArtifact.type === 'screenshot' && (
                  <button
                    style={{
                      padding: 'var(--spacing-sm) var(--spacing-md)',
                      backgroundColor: 'var(--color-bg-secondary)',
                      color: 'var(--color-text)',
                      border: '1px solid var(--color-border)',
                      borderRadius: '0.25rem',
                      cursor: 'pointer',
                    }}
                    onClick={() => {
                      // Would open image in lightbox
                      alert('Image preview would open here');
                    }}
                  >
                    Preview
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BrowserArtifacts;
