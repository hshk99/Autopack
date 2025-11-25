import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import RunProgress from './components/RunProgress'
import ModelMapping from './components/ModelMapping'
import UsagePanel from './components/UsagePanel'
import InterventionHelpers from './components/InterventionHelpers'
import './App.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 5000, // Poll every 5 seconds
      refetchOnWindowFocus: false,
    },
  },
})

function App() {
  const [selectedRunId, setSelectedRunId] = useState('run_test_dashboard')

  return (
    <QueryClientProvider client={queryClient}>
      <div className="dashboard">
        <header className="dashboard-header">
          <h1>Autopack Dashboard</h1>
          <div className="run-selector">
            <label>Run ID:</label>
            <input
              type="text"
              value={selectedRunId}
              onChange={(e) => setSelectedRunId(e.target.value)}
              placeholder="Enter run ID"
            />
          </div>
        </header>

        <div className="dashboard-grid">
          <div className="panel panel-progress">
            <h2>Run Progress</h2>
            <RunProgress runId={selectedRunId} />
          </div>

          <div className="panel panel-models">
            <h2>Model Mapping</h2>
            <ModelMapping runId={selectedRunId} />
          </div>

          <div className="panel panel-usage">
            <h2>Token Usage</h2>
            <UsagePanel />
          </div>

          <div className="panel panel-intervention">
            <h2>Intervention Helpers</h2>
            <InterventionHelpers runId={selectedRunId} />
          </div>
        </div>
      </div>
    </QueryClientProvider>
  )
}

export default App
