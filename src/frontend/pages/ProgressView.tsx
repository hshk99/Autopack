/**
 * Enhanced Progress Visualization with File Change Preview
 *
 * GAP-8.10.4 implementation
 * Shows: real-time progress, phase timeline, pending file changes
 * Note: Respects redaction/sanitization and governance boundaries
 */
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getRun, getRunStatus } from '../services/api';
import type { Run, DashboardRunStatus, DashboardTierStatus, DashboardPhaseStatus } from '../types';
import StatusBadge from '../components/StatusBadge';
import ProgressBar from '../components/ProgressBar';

interface FileChange {
  path: string;
  action: 'add' | 'modify' | 'delete';
  lines_added?: number;
  lines_removed?: number;
  preview?: string;
  is_redacted?: boolean;
}

interface PendingApproval {
  id: string;
  phase_id: string;
  description: string;
  files: FileChange[];
  created_at: string;
  requires_human_approval: boolean;
}

// Demo data for preview
const DEMO_PENDING_APPROVAL: PendingApproval = {
  id: 'approval-001',
  phase_id: 'T2.implement',
  description: 'Add user authentication module',
  created_at: new Date(Date.now() - 60000).toISOString(),
  requires_human_approval: true,
  files: [
    {
      path: 'src/auth/login.py',
      action: 'add',
      lines_added: 45,
      preview: `def login(username: str, password: str) -> Token:
    """Authenticate user and return JWT token."""
    user = db.get_user(username)
    if not user or not verify_password(password, user.hashed_password):
        raise AuthenticationError("Invalid credentials")
    return create_token(user)`,
    },
    {
      path: 'src/auth/models.py',
      action: 'add',
      lines_added: 28,
      preview: `class User(BaseModel):
    id: UUID
    username: str
    email: str
    hashed_password: str
    created_at: datetime`,
    },
    {
      path: 'src/api/routes.py',
      action: 'modify',
      lines_added: 12,
      lines_removed: 2,
      preview: `+from auth import login_router
+app.include_router(login_router, prefix="/auth")`,
    },
    {
      path: 'config/secrets.yaml',
      action: 'modify',
      is_redacted: true,
      preview: '[REDACTED - Contains sensitive configuration]',
    },
  ],
};

const ACTION_COLORS: Record<string, string> = {
  add: '#22c55e',
  modify: '#eab308',
  delete: '#ef4444',
};

const ACTION_ICONS: Record<string, string> = {
  add: '+',
  modify: '~',
  delete: '-',
};

const ProgressView: React.FC = () => {
  const { buildId } = useParams<{ buildId: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [status, setStatus] = useState<DashboardRunStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [apiAvailable, setApiAvailable] = useState(false);

  useEffect(() => {
    if (!buildId) return;

    const loadData = async () => {
      setLoading(true);
      try {
        const [runData, statusData] = await Promise.all([getRun(buildId), getRunStatus(buildId)]);
        setRun(runData);
        setStatus(statusData);
        setApiAvailable(true);
        // In real implementation, would fetch pending approvals from API
        // For now, show demo data if run is in progress
        if (statusData?.state === 'running') {
          setPendingApproval(DEMO_PENDING_APPROVAL);
        }
      } catch {
        setApiAvailable(false);
        // Use demo approval data
        setPendingApproval(DEMO_PENDING_APPROVAL);
      } finally {
        setLoading(false);
      }
    };

    loadData();

    // Poll for updates every 5 seconds
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [buildId]);

  const toggleFileExpanded = (path: string) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const getPhaseProgress = (): { completed: number; total: number; current: string } => {
    if (!status?.tiers) {
      return { completed: 0, total: 0, current: 'Unknown' };
    }
    let completed = 0;
    let total = 0;
    let current = '';
    for (const tier of status.tiers) {
      for (const phase of tier.phases || []) {
        total++;
        if (phase.state === 'completed') {
          completed++;
        } else if (phase.state === 'running' && !current) {
          current = phase.name;
        }
      }
    }
    return { completed, total, current: current || 'Waiting' };
  };

  const progress = getPhaseProgress();

  if (loading) {
    return (
      <div style={{ padding: 'var(--spacing-lg)', textAlign: 'center' }}>
        <p>Loading progress...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 'var(--spacing-lg)', maxWidth: '1000px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--spacing-lg)' }}>
        <Link
          to={`/builds/${buildId}`}
          style={{
            color: 'var(--color-text-secondary)',
            textDecoration: 'none',
            fontSize: '0.875rem',
          }}
        >
          ← Back to Run
        </Link>
        <h1 style={{ margin: 'var(--spacing-sm) 0 0' }}>Progress & Approvals</h1>
        <p style={{ color: 'var(--color-text-secondary)' }}>
          Run: {buildId} • {run?.goal_anchor || 'Loading...'}
        </p>
      </div>

      {/* API Notice */}
      {!apiAvailable && (
        <div
          style={{
            padding: 'var(--spacing-md)',
            backgroundColor: '#fffbeb',
            border: '1px solid var(--color-warning)',
            borderRadius: '0.5rem',
            marginBottom: 'var(--spacing-lg)',
          }}
        >
          <strong>Demo Mode:</strong> Showing sample data. Real-time progress API not yet connected.
        </div>
      )}

      {/* Overall Progress */}
      <div
        style={{
          padding: 'var(--spacing-lg)',
          backgroundColor: 'var(--color-bg)',
          border: '1px solid var(--color-border)',
          borderRadius: '0.5rem',
          marginBottom: 'var(--spacing-lg)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: 0 }}>Overall Progress</h3>
            <p style={{ color: 'var(--color-text-secondary)', margin: 'var(--spacing-xs) 0 0' }}>
              {progress.completed} of {progress.total} phases completed
            </p>
          </div>
          <StatusBadge
            status={status?.state || 'pending'}
            size="lg"
          />
        </div>

        <div style={{ marginTop: 'var(--spacing-md)' }}>
          <ProgressBar
            percent={progress.total > 0 ? (progress.completed / progress.total) * 100 : 0}
            color={status?.state === 'failed' ? 'error' : status?.state === 'completed' ? 'success' : 'primary'}
          />
        </div>

        {progress.current && progress.current !== 'Waiting' && (
          <div
            style={{
              marginTop: 'var(--spacing-sm)',
              fontSize: '0.875rem',
              color: 'var(--color-text-secondary)',
            }}
          >
            Current phase: <strong>{progress.current}</strong>
          </div>
        )}
      </div>

      {/* Phase Timeline */}
      <div
        style={{
          padding: 'var(--spacing-lg)',
          backgroundColor: 'var(--color-bg)',
          border: '1px solid var(--color-border)',
          borderRadius: '0.5rem',
          marginBottom: 'var(--spacing-lg)',
        }}
      >
        <h3 style={{ margin: '0 0 var(--spacing-md)' }}>Phase Timeline</h3>
        <div style={{ position: 'relative' }}>
          {status?.tiers?.map((tier: DashboardTierStatus, tierIndex: number) => (
            <div
              key={tier.name}
              style={{ marginBottom: tierIndex < (status.tiers?.length || 0) - 1 ? 'var(--spacing-md)' : 0 }}
            >
              <div
                style={{
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  color: 'var(--color-text-secondary)',
                  marginBottom: 'var(--spacing-sm)',
                }}
              >
                {tier.name}
              </div>
              <div style={{ display: 'flex', gap: 'var(--spacing-xs)', flexWrap: 'wrap' }}>
                {tier.phases?.map((phase: DashboardPhaseStatus) => (
                  <div
                    key={phase.id}
                    title={phase.name}
                    style={{
                      padding: 'var(--spacing-xs) var(--spacing-sm)',
                      backgroundColor:
                        phase.state === 'completed'
                          ? '#dcfce7'
                          : phase.state === 'running'
                            ? '#dbeafe'
                            : phase.state === 'failed'
                              ? '#fee2e2'
                              : 'var(--color-bg-secondary)',
                      color:
                        phase.state === 'completed'
                          ? '#166534'
                          : phase.state === 'running'
                            ? '#1e40af'
                            : phase.state === 'failed'
                              ? '#dc2626'
                              : 'var(--color-text-secondary)',
                      borderRadius: '0.25rem',
                      fontSize: '0.75rem',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {phase.state === 'running' && '▶ '}
                    {phase.state === 'completed' && '✓ '}
                    {phase.state === 'failed' && '✗ '}
                    {phase.name}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {!status?.tiers?.length && (
            <p style={{ color: 'var(--color-text-secondary)', fontStyle: 'italic' }}>
              No phase data available
            </p>
          )}
        </div>
      </div>

      {/* Pending Approval */}
      {pendingApproval && (
        <div
          style={{
            padding: 'var(--spacing-lg)',
            backgroundColor: '#fffbeb',
            border: '2px solid var(--color-warning)',
            borderRadius: '0.5rem',
            marginBottom: 'var(--spacing-lg)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
            <div>
              <h3 style={{ margin: 0, color: '#92400e' }}>⚠️ Pending Approval Required</h3>
              <p style={{ color: 'var(--color-text-secondary)', margin: 'var(--spacing-xs) 0 0' }}>
                {pendingApproval.description}
              </p>
              <p style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', margin: 'var(--spacing-xs) 0 0' }}>
                Phase: {pendingApproval.phase_id} •{' '}
                {new Date(pendingApproval.created_at).toLocaleString()}
              </p>
            </div>
          </div>

          {/* File Changes Preview */}
          <div style={{ marginTop: 'var(--spacing-md)' }}>
            <h4 style={{ margin: '0 0 var(--spacing-sm)', fontSize: '0.875rem' }}>
              Proposed File Changes ({pendingApproval.files.length} files)
            </h4>

            {pendingApproval.files.map((file) => (
              <div
                key={file.path}
                style={{
                  marginBottom: 'var(--spacing-sm)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '0.25rem',
                  backgroundColor: 'var(--color-bg)',
                }}
              >
                <div
                  onClick={() => !file.is_redacted && toggleFileExpanded(file.path)}
                  style={{
                    padding: 'var(--spacing-sm)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--spacing-sm)',
                    cursor: file.is_redacted ? 'not-allowed' : 'pointer',
                    backgroundColor: file.is_redacted ? '#fef2f2' : 'transparent',
                  }}
                >
                  <span
                    style={{
                      width: '20px',
                      height: '20px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: ACTION_COLORS[file.action],
                      color: '#fff',
                      borderRadius: '0.25rem',
                      fontWeight: 700,
                      fontSize: '0.875rem',
                    }}
                  >
                    {ACTION_ICONS[file.action]}
                  </span>
                  <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '0.875rem' }}>
                    {file.path}
                  </span>
                  {file.lines_added !== undefined && (
                    <span style={{ color: '#22c55e', fontSize: '0.75rem' }}>+{file.lines_added}</span>
                  )}
                  {file.lines_removed !== undefined && (
                    <span style={{ color: '#ef4444', fontSize: '0.75rem' }}>-{file.lines_removed}</span>
                  )}
                  {file.is_redacted && (
                    <span
                      style={{
                        fontSize: '0.75rem',
                        color: '#dc2626',
                        backgroundColor: '#fee2e2',
                        padding: '2px 6px',
                        borderRadius: '0.25rem',
                      }}
                    >
                      REDACTED
                    </span>
                  )}
                  {!file.is_redacted && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                      {expandedFiles.has(file.path) ? '▼' : '▶'}
                    </span>
                  )}
                </div>

                {expandedFiles.has(file.path) && file.preview && !file.is_redacted && (
                  <pre
                    style={{
                      margin: 0,
                      padding: 'var(--spacing-sm)',
                      backgroundColor: 'var(--color-bg-secondary)',
                      borderTop: '1px solid var(--color-border)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.75rem',
                      overflow: 'auto',
                      maxHeight: '200px',
                    }}
                  >
                    {file.preview}
                  </pre>
                )}
              </div>
            ))}
          </div>

          {/* Approval Actions */}
          <div
            style={{
              marginTop: 'var(--spacing-md)',
              display: 'flex',
              gap: 'var(--spacing-sm)',
              paddingTop: 'var(--spacing-md)',
              borderTop: '1px solid var(--color-border)',
            }}
          >
            <button
              style={{
                padding: 'var(--spacing-sm) var(--spacing-md)',
                backgroundColor: '#22c55e',
                color: '#fff',
                border: 'none',
                borderRadius: '0.25rem',
                cursor: 'pointer',
                fontWeight: 600,
              }}
              onClick={() => {
                alert('Approval would be sent to API');
              }}
            >
              ✓ Approve Changes
            </button>
            <button
              style={{
                padding: 'var(--spacing-sm) var(--spacing-md)',
                backgroundColor: '#ef4444',
                color: '#fff',
                border: 'none',
                borderRadius: '0.25rem',
                cursor: 'pointer',
                fontWeight: 600,
              }}
              onClick={() => {
                alert('Rejection would be sent to API');
              }}
            >
              ✗ Reject
            </button>
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
                alert('Request modifications dialog would open');
              }}
            >
              Request Changes
            </button>
          </div>
        </div>
      )}

      {/* No Pending Approvals */}
      {!pendingApproval && (
        <div
          style={{
            padding: 'var(--spacing-lg)',
            backgroundColor: 'var(--color-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: '0.5rem',
            textAlign: 'center',
            color: 'var(--color-text-secondary)',
          }}
        >
          <p>No pending approvals at this time.</p>
          <p style={{ fontSize: '0.875rem' }}>
            File change previews will appear here when the agent proposes modifications.
          </p>
        </div>
      )}
    </div>
  );
};

export default ProgressView;
