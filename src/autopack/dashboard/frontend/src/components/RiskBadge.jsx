import React from 'react'

/**
 * RiskBadge - Visual risk level indicator
 *
 * Phase 1: chatbot integration (risk scorer metadata)
 * Shows risk level from risk scorer + learned rules
 */
export default function RiskBadge({ riskLevel, riskScore, riskReasons, compact = false }) {
  const getRiskConfig = (level) => {
    const configs = {
      low: {
        emoji: '✅',
        color: '#3fb950',
        bgColor: 'rgba(63, 185, 80, 0.15)',
        label: 'Low Risk',
      },
      medium: {
        emoji: '⚠️',
        color: '#d29922',
        bgColor: 'rgba(210, 153, 34, 0.15)',
        label: 'Medium Risk',
      },
      high: {
        emoji: '🔴',
        color: '#f85149',
        bgColor: 'rgba(248, 81, 73, 0.15)',
        label: 'High Risk',
      },
      critical: {
        emoji: '🚨',
        color: '#da3633',
        bgColor: 'rgba(218, 54, 51, 0.25)',
        label: 'Critical Risk',
      },
    }

    return configs[level] || configs.medium
  }

  if (!riskLevel) {
    return null
  }

  const config = getRiskConfig(riskLevel)

  // Compact mode: just badge
  if (compact) {
    return (
      <span className="risk-badge-compact" style={{ background: config.bgColor, color: config.color }}>
        <span className="risk-emoji">{config.emoji}</span>
        <span className="risk-label">{config.label}</span>
        {riskScore !== undefined && (
          <span className="risk-score">{riskScore}/100</span>
        )}
        <style jsx>{`
          .risk-badge-compact {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
            white-space: nowrap;
          }

          .risk-emoji {
            font-size: 14px;
          }

          .risk-label {
            letter-spacing: 0.3px;
          }

          .risk-score {
            margin-left: 4px;
            opacity: 0.8;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 12px;
          }
        `}</style>
      </span>
    )
  }

  // Full mode: badge + reasons
  return (
    <div className="risk-badge-full">
      <div className="risk-header">
        <span className="risk-emoji">{config.emoji}</span>
        <span className="risk-label" style={{ color: config.color }}>
          {config.label}
        </span>
        {riskScore !== undefined && (
          <span className="risk-score">Score: {riskScore}/100</span>
        )}
      </div>

      {riskReasons && riskReasons.length > 0 && (
        <div className="risk-reasons">
          <div className="risk-reasons-title">Risk Factors:</div>
          <ul className="risk-reasons-list">
            {riskReasons.map((reason, idx) => (
              <li key={idx}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      <style jsx>{`
        .risk-badge-full {
          background: #161b22;
          border: 1px solid #30363d;
          border-radius: 6px;
          padding: 12px;
        }

        .risk-header {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 600;
        }

        .risk-emoji {
          font-size: 16px;
        }

        .risk-label {
          letter-spacing: 0.3px;
        }

        .risk-score {
          margin-left: auto;
          font-size: 12px;
          color: #8b949e;
          font-family: 'SF Mono', Monaco, monospace;
        }

        .risk-reasons {
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid #21262d;
        }

        .risk-reasons-title {
          font-size: 12px;
          color: #8b949e;
          margin-bottom: 8px;
          font-weight: 600;
        }

        .risk-reasons-list {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .risk-reasons-list li {
          font-size: 13px;
          color: #c9d1d9;
          padding-left: 16px;
          position: relative;
        }

        .risk-reasons-list li::before {
          content: '•';
          position: absolute;
          left: 4px;
          color: #58a6ff;
        }
      `}</style>
    </div>
  )
}
