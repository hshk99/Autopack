/**
 * Run card component for displaying run summary in inbox view
 *
 * GAP-8.10.2 implementation
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { StatusBadge } from './StatusBadge';
import { ProgressBar } from './ProgressBar';
import type { RunSummary, Run } from '../types';

interface RunCardProps {
  run: RunSummary | (Run & { percent_complete?: number; current_phase?: string });
  compact?: boolean;
}

export const RunCard: React.FC<RunCardProps> = ({ run, compact = false }) => {
  const percentComplete =
    'percent_complete' in run && run.percent_complete !== undefined ? run.percent_complete : 0;

  const tokenUtilization =
    run.token_cap > 0 ? Math.round((run.tokens_used / run.token_cap) * 100) : 0;

  const currentPhase = 'current_phase' in run ? run.current_phase : undefined;
  const hasErrors = 'has_errors' in run ? run.has_errors : false;

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <Link
      to={`/builds/${run.id}`}
      style={{
        display: 'block',
        padding: compact ? 'var(--spacing-sm)' : 'var(--spacing-md)',
        border: '1px solid var(--color-border)',
        borderRadius: '0.5rem',
        backgroundColor: 'var(--color-bg)',
        textDecoration: 'none',
        color: 'inherit',
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
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: 'var(--spacing-sm)',
        }}
      >
        <div>
          <div
            style={{
              fontWeight: 600,
              fontSize: compact ? '0.875rem' : '1rem',
              marginBottom: '0.25rem',
            }}
          >
            {run.id}
          </div>
          {run.goal_anchor && (
            <div
              style={{
                fontSize: '0.875rem',
                color: 'var(--color-text-secondary)',
                maxWidth: '300px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {run.goal_anchor}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 'var(--spacing-sm)', alignItems: 'center' }}>
          {hasErrors && (
            <span
              style={{
                color: 'var(--color-error)',
                fontSize: '0.75rem',
                fontWeight: 500,
              }}
            >
              ⚠ Errors
            </span>
          )}
          <StatusBadge status={run.state} size={compact ? 'sm' : 'md'} />
        </div>
      </div>

      {/* Progress */}
      {!compact && (
        <div style={{ marginBottom: 'var(--spacing-sm)' }}>
          <ProgressBar
            percent={percentComplete}
            label="Progress"
            color={run.state.startsWith('DONE_FAILED') ? 'error' : 'primary'}
          />
        </div>
      )}

      {/* Footer */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: '0.75rem',
          color: 'var(--color-text-secondary)',
        }}
      >
        <span>
          Tokens: {run.tokens_used.toLocaleString()} / {run.token_cap.toLocaleString()} (
          {tokenUtilization}%)
        </span>
        {currentPhase && <span>Phase: {currentPhase}</span>}
        <span>{formatDate(run.updated_at)}</span>
      </div>
    </Link>
  );
};

export default RunCard;
