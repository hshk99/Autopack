import React from 'react';
import { DoctorMetrics } from './DoctorMetrics';
import { DiagnosticsSummary } from './DiagnosticsSummary';

export const Dashboard: React.FC = () => {
  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>AutoPack Supervisor Dashboard</h1>
        <div className="status-indicator">
          <span className="status-dot active"></span>
          <span>Active</span>
        </div>
      </header>

      <main className="dashboard-content">
        <section className="metrics-section">
          <DoctorMetrics />
        </section>
        <section className="metrics-section">
          <DiagnosticsSummary />
        </section>
      </main>
    </div>
  );
};
