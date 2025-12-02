import React, { useEffect, useState } from 'react';

interface DoctorStats {
  total_calls: number;
  cheap_calls: number;
  strong_calls: number;
  escalations: number;
  cheap_ratio: number;
  strong_ratio: number;
  escalation_rate: number;
  action_distribution: Record<string, number>;
  total_cost: number;
}

export const DoctorMetrics: React.FC = () => {
  const [stats, setStats] = useState<DoctorStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch('/api/doctor-stats');
        if (!response.ok) {
          throw new Error('Failed to fetch Doctor stats');
        }
        const data = await response.json();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="doctor-metrics loading">Loading Doctor metrics...</div>;
  if (error) return <div className="doctor-metrics error">Error: {error}</div>;
  if (!stats) return null;

  return (
    <div className="doctor-metrics">
      <h2>Doctor Agent Metrics</h2>
      
      <div className="metrics-grid">
        <div className="metric-card">
          <h3>Total Calls</h3>
          <div className="metric-value">{stats.total_calls}</div>
        </div>

        <div className="metric-card">
          <h3>Model Distribution</h3>
          <div className="metric-breakdown">
            <div>Cheap: {stats.cheap_calls} ({(stats.cheap_ratio * 100).toFixed(0)}%)</div>
            <div>Strong: {stats.strong_calls} ({(stats.strong_ratio * 100).toFixed(0)}%)</div>
          </div>
        </div>

        <div className="metric-card">
          <h3>Escalations</h3>
          <div className="metric-value">{stats.escalations}</div>
          <div className="metric-subtitle">
            Rate: {(stats.escalation_rate * 100).toFixed(1)}%
          </div>
        </div>

        <div className="metric-card">
          <h3>Total Cost</h3>
          <div className="metric-value">${stats.total_cost.toFixed(4)}</div>
        </div>
      </div>

      <div className="action-distribution">
        <h3>Action Distribution</h3>
        <div className="action-list">
          {Object.entries(stats.action_distribution).map(([action, count]) => (
            <div key={action} className="action-item">
              <span className="action-name">{action}</span>
              <span className="action-count">{count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
