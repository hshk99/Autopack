import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

const API_BASE = 'http://localhost:8000'

export default function UsagePanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['usage'],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE}/dashboard/usage?period=week`)
      return response.data
    },
  })

  if (isLoading) return <div className="loading">Loading usage data...</div>

  const getUsageClass = (percent) => {
    if (percent > 90) return 'danger'
    if (percent > 80) return 'warning'
    return ''
  }

  return (
    <div>
      {data?.providers && data.providers.length > 0 ? (
        data.providers.map((provider) => (
          <div key={provider.provider} className="usage-card">
            <h3>{provider.provider.toUpperCase()}</h3>
            <div style={{ fontSize: '12px', color: '#8b949e' }}>
              {(provider.total_tokens / 1000000).toFixed(2)}M / {(provider.cap_tokens / 1000000).toFixed(0)}M tokens
            </div>
            <div className="usage-bar">
              <div
                className={`usage-fill ${getUsageClass(provider.percent_of_cap)}`}
                style={{ width: `${Math.min(provider.percent_of_cap, 100)}%` }}
              />
            </div>
            <div style={{ fontSize: '14px', fontWeight: '600' }}>
              {provider.percent_of_cap.toFixed(1)}% used
            </div>
          </div>
        ))
      ) : (
        <div className="loading">No usage data recorded yet</div>
      )}

      {data?.models && data.models.length > 0 && (
        <div style={{ marginTop: '20px' }}>
          <h3 style={{ fontSize: '14px', marginBottom: '12px', color: '#58a6ff' }}>Model Usage</h3>
          <table className="model-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Tokens</th>
              </tr>
            </thead>
            <tbody>
              {data.models.slice(0, 5).map((model, idx) => (
                <tr key={idx}>
                  <td>{model.model}</td>
                  <td>{(model.total_tokens / 1000000).toFixed(2)}M</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
