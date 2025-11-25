import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

const API_BASE = 'http://localhost:8000'

export default function RunProgress({ runId }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['runStatus', runId],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE}/dashboard/runs/${runId}/status`)
      return response.data
    },
    enabled: !!runId,
  })

  if (isLoading) return <div className="loading">Loading run progress...</div>
  if (error) return <div className="error-message">Run not found or error loading data</div>

  if (!data) return <div>No run selected</div>

  const getUsageColor = (utilization) => {
    if (utilization > 0.9) return 'danger'
    if (utilization > 0.8) return 'warning'
    return ''
  }

  return (
    <div>
      <div className="stat-item">
        <div className="stat-label">Status</div>
        <div className="stat-value">{data.state}</div>
      </div>

      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${data.percent_complete}%` }}
        >
          {Math.round(data.percent_complete)}%
        </div>
      </div>

      <div style={{ marginBottom: '8px', color: '#8b949e', fontSize: '14px' }}>
        {data.current_tier_name && data.current_phase_name ? (
          <>
            <strong>Current:</strong> {data.current_tier_name} / {data.current_phase_name}
          </>
        ) : (
          'Run not started or completed'
        )}
      </div>

      <div className="stat-grid">
        <div className="stat-item">
          <div className="stat-label">Tiers</div>
          <div className="stat-value">{data.completed_tiers} / {data.total_tiers}</div>
        </div>
        <div className="stat-item">
          <div className="stat-label">Phases</div>
          <div className="stat-value">{data.completed_phases} / {data.total_phases}</div>
        </div>
        <div className="stat-item">
          <div className="stat-label">Token Usage</div>
          <div className="stat-value">
            {(data.tokens_used / 1000000).toFixed(2)}M / {(data.token_cap / 1000000).toFixed(0)}M
          </div>
        </div>
        <div className="stat-item">
          <div className="stat-label">Issues</div>
          <div className="stat-value">
            {data.minor_issues_count} minor / {data.major_issues_count} major
          </div>
        </div>
      </div>
    </div>
  )
}
