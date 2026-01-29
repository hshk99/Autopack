/**
 * Metrics page with Pipeline Health Dashboard
 *
 * IMP-TELE-010: Real-time pipeline health dashboard for operational visibility.
 * Displays latency metrics, SLA compliance status, and component health indicators.
 */
import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api/client';

/**
 * Type definitions for Pipeline Health API response
 */
interface LatencyMetrics {
  telemetry_to_analysis_ms: number;
  analysis_to_task_ms: number;
  total_latency_ms: number;
  sla_threshold_ms: number;
  stage_latencies: Record<string, number | null>;
}

interface SLAComplianceMetrics {
  status: string;
  is_within_sla: boolean;
  breach_amount_ms: number;
  threshold_ms: number;
  active_breaches: Array<{
    level: string;
    stage_from: string | null;
    stage_to: string | null;
    message: string;
  }>;
}

interface ComponentHealthMetrics {
  component: string;
  status: string;
  score: number;
  issues: string[];
}

interface PipelineHealthResponse {
  timestamp: string;
  latency: LatencyMetrics;
  sla_compliance: SLAComplianceMetrics;
  component_health: Record<string, ComponentHealthMetrics>;
  overall_health_score: number;
  overall_status: string;
}

/**
 * Format milliseconds to human-readable duration
 */
const formatLatency = (ms: number): string => {
  if (ms === 0) return '0ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};

/**
 * Get color based on health score (0.0 - 1.0)
 */
const getScoreColor = (score: number): string => {
  if (score >= 0.8) return '#28a745'; // Green
  if (score >= 0.6) return '#ffc107'; // Yellow
  if (score >= 0.4) return '#fd7e14'; // Orange
  return '#dc3545'; // Red
};

/**
 * Get color based on status string
 */
const getStatusColor = (status: string): string => {
  switch (status.toLowerCase()) {
    case 'healthy':
    case 'excellent':
    case 'stable':
    case 'improving':
      return '#28a745';
    case 'degraded':
    case 'good':
    case 'acceptable':
    case 'warning':
      return '#ffc107';
    case 'attention_required':
    case 'degrading':
    case 'breached':
      return '#dc3545';
    default:
      return '#6c757d';
  }
};

/**
 * Pipeline Health Dashboard component
 *
 * IMP-TELE-010: Displays real-time pipeline health metrics including
 * latency charts, SLA status, and component health indicators.
 */
const PipelineHealthDashboard: React.FC = () => {
  const [health, setHealth] = useState<PipelineHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch('/metrics/pipeline-health');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const data: PipelineHealthResponse = await response.json();
      setHealth(data);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load pipeline health');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1>Pipeline Health Dashboard</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {lastRefresh && (
            <span style={{ color: '#666', fontSize: '14px' }}>
              Last updated: {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchHealth}
            disabled={loading}
            style={{
              padding: '8px 16px',
              backgroundColor: '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          padding: '15px',
          backgroundColor: '#f8d7da',
          color: '#721c24',
          borderRadius: '4px',
          marginBottom: '20px',
        }}>
          Error: {error}
        </div>
      )}

      {!loading && !error && health && (
        <>
          {/* Overall Status Banner */}
          <div style={{
            padding: '20px',
            backgroundColor: getStatusColor(health.overall_status) + '20',
            border: `2px solid ${getStatusColor(health.overall_status)}`,
            borderRadius: '8px',
            marginBottom: '30px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <div>
              <div style={{ fontSize: '14px', color: '#666', marginBottom: '4px' }}>Overall Status</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: getStatusColor(health.overall_status) }}>
                {health.overall_status.replace('_', ' ').toUpperCase()}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '14px', color: '#666', marginBottom: '4px' }}>Health Score</div>
              <div style={{ fontSize: '32px', fontWeight: 'bold', color: getScoreColor(health.overall_health_score) }}>
                {(health.overall_health_score * 100).toFixed(0)}%
              </div>
            </div>
          </div>

          {/* Metrics Cards Row */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '20px',
            marginBottom: '30px',
          }}>
            {/* Latency Card */}
            <div style={{
              padding: '20px',
              backgroundColor: '#f8f9fa',
              borderRadius: '8px',
              border: '1px solid #e9ecef',
            }}>
              <h3 style={{ margin: '0 0 15px 0', fontSize: '16px', color: '#495057' }}>Latency Metrics</h3>
              <div style={{ marginBottom: '10px' }}>
                <div style={{ fontSize: '12px', color: '#666' }}>Telemetry → Analysis</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                  {formatLatency(health.latency.telemetry_to_analysis_ms)}
                </div>
              </div>
              <div style={{ marginBottom: '10px' }}>
                <div style={{ fontSize: '12px', color: '#666' }}>Analysis → Task</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                  {formatLatency(health.latency.analysis_to_task_ms)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#666' }}>Total End-to-End</div>
                <div style={{
                  fontSize: '20px',
                  fontWeight: 'bold',
                  color: health.latency.total_latency_ms <= health.latency.sla_threshold_ms ? '#28a745' : '#dc3545',
                }}>
                  {formatLatency(health.latency.total_latency_ms)}
                  <span style={{ fontSize: '12px', color: '#666', fontWeight: 'normal' }}>
                    {' '}/ {formatLatency(health.latency.sla_threshold_ms)}
                  </span>
                </div>
              </div>
            </div>

            {/* SLA Compliance Card */}
            <div style={{
              padding: '20px',
              backgroundColor: '#f8f9fa',
              borderRadius: '8px',
              border: '1px solid #e9ecef',
            }}>
              <h3 style={{ margin: '0 0 15px 0', fontSize: '16px', color: '#495057' }}>SLA Compliance</h3>
              <div style={{
                fontSize: '24px',
                fontWeight: 'bold',
                color: getStatusColor(health.sla_compliance.status),
                marginBottom: '10px',
              }}>
                {health.sla_compliance.status.toUpperCase()}
              </div>
              <div style={{ marginBottom: '10px' }}>
                <span style={{
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  backgroundColor: health.sla_compliance.is_within_sla ? '#d4edda' : '#f8d7da',
                  color: health.sla_compliance.is_within_sla ? '#155724' : '#721c24',
                }}>
                  {health.sla_compliance.is_within_sla ? 'Within SLA' : 'SLA Breached'}
                </span>
              </div>
              {health.sla_compliance.breach_amount_ms > 0 && (
                <div style={{ color: '#dc3545', fontSize: '14px' }}>
                  Breach: +{formatLatency(health.sla_compliance.breach_amount_ms)}
                </div>
              )}
              {health.sla_compliance.active_breaches.length > 0 && (
                <div style={{ marginTop: '10px' }}>
                  <div style={{ fontSize: '12px', color: '#666', marginBottom: '5px' }}>Active Alerts:</div>
                  {health.sla_compliance.active_breaches.map((breach, idx) => (
                    <div key={idx} style={{
                      fontSize: '11px',
                      color: breach.level === 'critical' ? '#dc3545' : '#ffc107',
                      padding: '4px',
                      backgroundColor: breach.level === 'critical' ? '#f8d7da' : '#fff3cd',
                      borderRadius: '3px',
                      marginBottom: '4px',
                    }}>
                      [{breach.level}] {breach.message}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Health Score Gauge */}
            <div style={{
              padding: '20px',
              backgroundColor: '#f8f9fa',
              borderRadius: '8px',
              border: '1px solid #e9ecef',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <h3 style={{ margin: '0 0 15px 0', fontSize: '16px', color: '#495057' }}>Health Score</h3>
              <div style={{
                width: '120px',
                height: '120px',
                borderRadius: '50%',
                background: `conic-gradient(${getScoreColor(health.overall_health_score)} ${health.overall_health_score * 360}deg, #e9ecef 0deg)`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <div style={{
                  width: '90px',
                  height: '90px',
                  borderRadius: '50%',
                  backgroundColor: '#f8f9fa',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '24px',
                  fontWeight: 'bold',
                  color: getScoreColor(health.overall_health_score),
                }}>
                  {(health.overall_health_score * 100).toFixed(0)}%
                </div>
              </div>
            </div>
          </div>

          {/* Component Health Section */}
          <h2 style={{ marginBottom: '15px' }}>Component Health</h2>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '15px',
          }}>
            {Object.entries(health.component_health).map(([name, component]) => (
              <div key={name} style={{
                padding: '15px',
                backgroundColor: '#fff',
                borderRadius: '8px',
                border: `2px solid ${getScoreColor(component.score)}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div style={{ fontWeight: 'bold', fontSize: '14px' }}>{name}</div>
                  <div style={{
                    padding: '2px 8px',
                    borderRadius: '12px',
                    fontSize: '12px',
                    backgroundColor: getStatusColor(component.status) + '20',
                    color: getStatusColor(component.status),
                  }}>
                    {component.status}
                  </div>
                </div>
                <div style={{ marginBottom: '10px' }}>
                  <div style={{
                    height: '8px',
                    backgroundColor: '#e9ecef',
                    borderRadius: '4px',
                    overflow: 'hidden',
                  }}>
                    <div style={{
                      width: `${component.score * 100}%`,
                      height: '100%',
                      backgroundColor: getScoreColor(component.score),
                      transition: 'width 0.3s ease',
                    }} />
                  </div>
                  <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>
                    Score: {(component.score * 100).toFixed(0)}%
                  </div>
                </div>
                {component.issues.length > 0 && (
                  <div>
                    <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>Issues:</div>
                    {component.issues.map((issue, idx) => (
                      <div key={idx} style={{
                        fontSize: '11px',
                        color: '#dc3545',
                        padding: '4px',
                        backgroundColor: '#f8d7da',
                        borderRadius: '3px',
                        marginBottom: '3px',
                      }}>
                        {issue}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Stage Latencies Detail */}
          {Object.keys(health.latency.stage_latencies).length > 0 && (
            <>
              <h2 style={{ marginTop: '30px', marginBottom: '15px' }}>Stage Latencies</h2>
              <table style={{
                width: '100%',
                borderCollapse: 'collapse',
                backgroundColor: '#fff',
                borderRadius: '8px',
                overflow: 'hidden',
              }}>
                <thead>
                  <tr style={{ backgroundColor: '#f8f9fa' }}>
                    <th style={{ padding: '12px', textAlign: 'left', borderBottom: '2px solid #dee2e6' }}>Stage Transition</th>
                    <th style={{ padding: '12px', textAlign: 'right', borderBottom: '2px solid #dee2e6' }}>Latency</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(health.latency.stage_latencies).map(([stage, latency]) => (
                    <tr key={stage} style={{ borderBottom: '1px solid #dee2e6' }}>
                      <td style={{ padding: '12px' }}>
                        {stage.replace(/_to_/g, ' → ').replace(/_/g, ' ')}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontFamily: 'monospace' }}>
                        {latency !== null ? formatLatency(latency) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}

      {loading && !health && (
        <div style={{ textAlign: 'center', padding: '50px', color: '#666' }}>
          Loading pipeline health data...
        </div>
      )}
    </div>
  );
};

/**
 * Metrics page component
 *
 * IMP-TELE-010: Main metrics page containing the Pipeline Health Dashboard
 */
const Metrics: React.FC = () => {
  return <PipelineHealthDashboard />;
};

export default Metrics;
