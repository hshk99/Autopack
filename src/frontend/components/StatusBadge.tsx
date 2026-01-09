/**
 * Status badge component for displaying run/phase/tier states
 *
 * GAP-8.10.x implementation
 */
import React from 'react';
import type { RunState, PhaseState, TierState } from '../types';

type StatusType = RunState | PhaseState | TierState | string;

interface StatusBadgeProps {
  status: StatusType;
  size?: 'sm' | 'md' | 'lg';
}

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  // Success states
  DONE_SUCCESS: { bg: 'var(--color-success)', text: '#fff' },
  COMPLETE: { bg: 'var(--color-success)', text: '#fff' },

  // In-progress states
  QUEUED: { bg: 'var(--color-bg-secondary)', text: 'var(--color-text)' },
  PENDING: { bg: 'var(--color-bg-secondary)', text: 'var(--color-text)' },
  PLAN_BOOTSTRAP: { bg: 'var(--color-primary)', text: '#fff' },
  RUN_CREATED: { bg: 'var(--color-primary)', text: '#fff' },
  PHASE_QUEUEING: { bg: 'var(--color-primary)', text: '#fff' },
  PHASE_EXECUTION: { bg: 'var(--color-primary)', text: '#fff' },
  EXECUTING: { bg: 'var(--color-primary)', text: '#fff' },
  IN_PROGRESS: { bg: 'var(--color-primary)', text: '#fff' },
  GATE: { bg: 'var(--color-warning)', text: '#000' },
  CI_RUNNING: { bg: 'var(--color-warning)', text: '#000' },
  SNAPSHOT_CREATED: { bg: 'var(--color-primary-dark)', text: '#fff' },

  // Failed states
  DONE_FAILED_BUDGET_EXHAUSTED: { bg: 'var(--color-error)', text: '#fff' },
  DONE_FAILED_POLICY_VIOLATION: { bg: 'var(--color-error)', text: '#fff' },
  DONE_FAILED_REQUIRES_HUMAN_REVIEW: { bg: 'var(--color-warning)', text: '#000' },
  DONE_FAILED_ENVIRONMENT: { bg: 'var(--color-error)', text: '#fff' },
  FAILED: { bg: 'var(--color-error)', text: '#fff' },

  // Skipped
  SKIPPED: { bg: 'var(--color-text-secondary)', text: '#fff' },
};

const SIZE_CLASSES = {
  sm: { padding: '0.125rem 0.5rem', fontSize: '0.75rem' },
  md: { padding: '0.25rem 0.75rem', fontSize: '0.875rem' },
  lg: { padding: '0.375rem 1rem', fontSize: '1rem' },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md' }) => {
  const colors = STATUS_COLORS[status] || {
    bg: 'var(--color-bg-secondary)',
    text: 'var(--color-text)',
  };
  const sizeStyle = SIZE_CLASSES[size];

  // Format display text
  const displayText = status
    .replace(/^DONE_/, '')
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <span
      style={{
        display: 'inline-block',
        padding: sizeStyle.padding,
        fontSize: sizeStyle.fontSize,
        fontWeight: 500,
        borderRadius: '0.25rem',
        backgroundColor: colors.bg,
        color: colors.text,
        whiteSpace: 'nowrap',
      }}
    >
      {displayText}
    </span>
  );
};

export default StatusBadge;
