import React, { useEffect, useState } from 'react';

interface DoctorStats {
  current_run: {
    total_calls: number;
    cheap_calls: number;
    strong_calls: number;
    escalations: number;
    escalation_rate: number;
    cheap_ratio: number;
    strong_ratio: number;
    action_distribution: Record<string, number>;
  };
  historical: {
    total_calls: number;
    cheap_calls: number;
    strong_calls: number;
    action_distribution: Record<string, number>;
  };
}

interface DoctorMetricsProps {
  apiKey: string;
  runId?: number;
  refreshInterval?: number;
}

export const DoctorMetrics: React.FC<DoctorMetricsProps> = ({
  apiKey,
  runId,
  refreshInterval = 5000,
}) => {
  const [stats, setStats] = useState<DoctorStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    try {
      const url = runId
        ? `/api/doctor-stats?run_id=${runId}`
        : '/api/doctor-stats';
      
      const response = await fetch(url, {
        headers: {
          'X-API-Key': apiKey,
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch stats');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, refreshInterval);
    return () => clearInterval(interval);
  }, [apiKey, runId, refreshInterval]);

  if (loading) {
    return <div className="doctor-metrics loading">Loading Doctor metrics...</div>;
  }

  if (error) {
    return <div className="doctor-metrics error">Error: {error}</div>;
  }

  if (!stats) {
    return <div className="doctor-metrics empty">No Doctor data available</div>;
  }

  const { current_run, historical } = stats;

  return (
    <div className="doctor-metrics">
      <h2>🩺 Doctor Usage Metrics</h2>
      
      <div className="metrics-section">
        <h3>Current Run</h3>
        <div className="metrics-grid">
          <div className="metric-card">
            <span className="metric-value">{current_run.total_calls}</span>
            <span className="metric-label">Total Calls</span>
          </div>
          <div className="metric-card">
            <span className="metric-value">{current_run.cheap_ratio}%</span>
            <span className="metric-label">Cheap Model Usage</span>
          </div>
          <div className="metric-card">
            <span className="metric-value">{current_run.strong_ratio}%</span>
            <span className="metric-label">Strong Model Usage</span>
          </div>
          <div className="metric-card">
            <span className="metric-value">{current_run.escalations}</span>
            <span className="metric-label">Escalations ({current_run.escalation_rate}%)</span>
          </div>
        </div>

        <div className="action-distribution">
          <h4>Action Distribution</h4>
          <div className="pie-chart-data">
            {Object.entries(current_run.action_distribution).length > 0 ? (
              <ul>
                {Object.entries(current_run.action_distribution).map(([action, count]) => (
                  <li key={action}>
                    <span className="action-name">{action}</span>
                    <span className="action-count">{count}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No actions recorded yet</p>
            )}
          </div>
        </div>
      </div>

      <div className="metrics-section">
        <h3>Historical (All Runs)</h3>
        <div className="metrics-grid">
          <div className="metric-card">
            <span className="metric-value">{historical.total_calls}</span>
            <span className="metric-label">Total Calls</span>
          </div>
          <div className="metric-card">
            <span className="metric-value">{historical.cheap_calls}</span>
            <span className="metric-label">Cheap Calls</span>
          </div>
          <div className="metric-card">
            <span className="metric-value">{historical.strong_calls}</span>
            <span className="metric-label">Strong Calls</span>
          </div>
        </div>

        <div className="action-distribution">
          <h4>Historical Actions</h4>
          <ul>
            {Object.entries(historical.action_distribution).map(([action, count]) => (
              <li key={action}>
                <span className="action-name">{action}</span>
                <span className="action-count">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};
