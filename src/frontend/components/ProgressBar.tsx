/**
 * Progress bar component with percentage display
 *
 * GAP-8.10.x implementation
 */
import React from 'react';

interface ProgressBarProps {
  percent: number;
  label?: string;
  showPercent?: boolean;
  height?: number;
  color?: 'primary' | 'success' | 'warning' | 'error';
}

const COLOR_MAP = {
  primary: 'var(--color-primary)',
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  error: 'var(--color-error)',
};

export const ProgressBar: React.FC<ProgressBarProps> = ({
  percent,
  label,
  showPercent = true,
  height = 8,
  color = 'primary',
}) => {
  const clampedPercent = Math.max(0, Math.min(100, percent));
  const barColor = COLOR_MAP[color];

  return (
    <div style={{ width: '100%' }}>
      {(label || showPercent) && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: '0.25rem',
            fontSize: '0.875rem',
            color: 'var(--color-text-secondary)',
          }}
        >
          {label && <span>{label}</span>}
          {showPercent && <span>{Math.round(clampedPercent)}%</span>}
        </div>
      )}
      <div
        style={{
          width: '100%',
          height: `${height}px`,
          backgroundColor: 'var(--color-border)',
          borderRadius: `${height / 2}px`,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${clampedPercent}%`,
            height: '100%',
            backgroundColor: barColor,
            borderRadius: `${height / 2}px`,
            transition: 'width 0.3s ease',
          }}
        />
      </div>
    </div>
  );
};

export default ProgressBar;
