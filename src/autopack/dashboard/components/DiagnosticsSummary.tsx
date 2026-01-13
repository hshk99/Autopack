import React, { useEffect, useState } from 'react';

interface ProbeSummary {
  name: string;
  commands: string[];
  resolved: boolean;
}

interface DiagnosticsSummaryPayload {
  run_id: string | null;
  phase_id: string | null;
  failure_class: string | null;
  ledger: string | null;
  probes: ProbeSummary[];
  timestamp: number | null;
  path?: string;
}

export const DiagnosticsSummary: React.FC = () => {
  const [data, setData] = useState<DiagnosticsSummaryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDiagnostics = async () => {
      try {
        const resp = await fetch('/api/diagnostics/latest');
        if (!resp.ok) throw new Error('Failed to load diagnostics');
        const json = await resp.json();
        setData(json);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };
    fetchDiagnostics();
    const interval = setInterval(fetchDiagnostics, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="diag-card">Loading diagnostics…</div>;
  if (error) return <div className="diag-card error">Diagnostics error: {error}</div>;
  if (!data) return null;

  return (
    <div className="diag-card">
      <div className="diag-header">
        <div>
          <h2>Latest Diagnostics</h2>
          <div className="diag-meta">
            <span>Run: {data.run_id || 'n/a'}</span>
            <span>Phase: {data.phase_id || 'n/a'}</span>
            <span>Failure: {data.failure_class || 'n/a'}</span>
          </div>
        </div>
        {data.timestamp && (
          <div className="diag-ts">
            {new Date(data.timestamp * 1000).toLocaleString()}
          </div>
        )}
      </div>
      <div className="diag-ledger">
        {data.ledger || 'No diagnostics available'}
      </div>
      <div className="diag-probes">
        {data.probes?.map((probe) => (
          <div key={probe.name} className="probe-item">
            <div className="probe-title">
              {probe.name} {probe.resolved ? '✅' : 'ℹ️'}
            </div>
            <div className="probe-commands">
              {probe.commands.join(', ')}
            </div>
          </div>
        ))}
      </div>
      {data.path && (
        <div className="diag-path">File: {data.path}</div>
      )}
    </div>
  );
};
