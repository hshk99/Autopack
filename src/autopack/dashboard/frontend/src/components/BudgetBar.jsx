import React from 'react'

/**
 * BudgetBar - Visual token/time budget display
 *
 * Phase 1: chatbot integration
 * Shows token usage and optional time budget with visual bars
 */
export default function BudgetBar({
  tokensUsed,
  tokenCap,
  elapsedSec,
  maxWallClockSec
}) {
  const tokenPercent = tokenCap > 0 ? (tokensUsed / tokenCap) * 100 : 0
  const timePercent = maxWallClockSec > 0 ? (elapsedSec / maxWallClockSec) * 100 : 0

  const getUsageClass = (percent) => {
    if (percent > 90) return 'danger'
    if (percent > 80) return 'warning'
    return 'ok'
  }

  const formatDuration = (seconds) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)

    if (hours > 0) {
      return `${hours}h ${minutes}m`
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`
    } else {
      return `${secs}s`
    }
  }

  return (
    <div className="budget-bar-container">
      {/* Token Budget */}
      <div className="budget-section">
        <div className="budget-header">
          <span className="budget-label">Token Budget</span>
          <span className="budget-value">
            {(tokensUsed / 1000).toFixed(1)}K / {(tokenCap / 1000).toFixed(0)}K
          </span>
        </div>
        <div className="usage-bar">
          <div
            className={`usage-fill ${getUsageClass(tokenPercent)}`}
            style={{ width: `${Math.min(tokenPercent, 100)}%` }}
          />
        </div>
        <div className="budget-percent">
          {tokenPercent.toFixed(1)}% used
        </div>
      </div>

      {/* Time Budget (if available) */}
      {maxWallClockSec > 0 && (
        <div className="budget-section" style={{ marginTop: '16px' }}>
          <div className="budget-header">
            <span className="budget-label">Time Budget</span>
            <span className="budget-value">
              {formatDuration(elapsedSec)} / {formatDuration(maxWallClockSec)}
            </span>
          </div>
          <div className="usage-bar">
            <div
              className={`usage-fill ${getUsageClass(timePercent)}`}
              style={{ width: `${Math.min(timePercent, 100)}%` }}
            />
          </div>
          <div className="budget-percent">
            {timePercent.toFixed(1)}% used
          </div>
        </div>
      )}

      <style jsx>{`
        .budget-bar-container {
          background: #161b22;
          border: 1px solid #30363d;
          border-radius: 6px;
          padding: 16px;
        }

        .budget-section {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .budget-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .budget-label {
          font-size: 14px;
          font-weight: 600;
          color: #c9d1d9;
        }

        .budget-value {
          font-size: 13px;
          color: #8b949e;
          font-family: 'SF Mono', Monaco, monospace;
        }

        .usage-bar {
          width: 100%;
          height: 8px;
          background: #21262d;
          border-radius: 4px;
          overflow: hidden;
        }

        .usage-fill {
          height: 100%;
          transition: width 0.3s ease;
        }

        .usage-fill.ok {
          background: #58a6ff;
        }

        .usage-fill.warning {
          background: #d29922;
        }

        .usage-fill.danger {
          background: #f85149;
        }

        .budget-percent {
          font-size: 12px;
          color: #8b949e;
          text-align: right;
        }
      `}</style>
    </div>
  )
}
