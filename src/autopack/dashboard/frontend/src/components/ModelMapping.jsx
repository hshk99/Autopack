import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

const API_BASE = 'http://localhost:8000'

export default function ModelMapping({ runId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE}/dashboard/models`)
      return response.data
    },
  })

  if (isLoading) return <div className="loading">Loading model mappings...</div>

  // Group by role and filter to show only key categories
  const keyCategories = ['external_feature_reuse', 'security_auth_change', 'general']
  const filteredMappings = data?.filter(m =>
    keyCategories.includes(m.category) && m.complexity === 'medium'
  ) || []

  return (
    <div>
      <div style={{ marginBottom: '12px', fontSize: '13px', color: '#8b949e' }}>
        Showing key categories (medium complexity)
      </div>
      <table className="model-table">
        <thead>
          <tr>
            <th>Role</th>
            <th>Category</th>
            <th>Model</th>
          </tr>
        </thead>
        <tbody>
          {filteredMappings.map((mapping, idx) => (
            <tr key={idx}>
              <td style={{ textTransform: 'capitalize' }}>{mapping.role}</td>
              <td style={{ fontSize: '11px' }}>{mapping.category.replace(/_/g, ' ')}</td>
              <td>
                <select
                  value={mapping.model}
                  onChange={async (e) => {
                    // TODO: Implement model override API call
                    console.log('Model change:', { ...mapping, model: e.target.value })
                  }}
                >
                  <option value={mapping.model}>{mapping.model}</option>
                  <option value="gpt-4o">gpt-4o</option>
                  <option value="gpt-4o-mini">gpt-4o-mini</option>
                  <option value="claude-3-5-sonnet-20241022">claude-3-5-sonnet</option>
                  <option value="glm-4.5-20250101">glm-4.5</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: '12px', fontSize: '12px', color: '#8b949e' }}>
        Note: Model changes affect new runs only (global scope)
      </div>
    </div>
  )
}
