/**
 * Dashboard page component
 *
 * Main landing page showing build overview and system status
 * GAP-8.10.x: Added navigation links to Runs Inbox
 */
import React from 'react';
import { Link } from 'react-router-dom';

const Dashboard: React.FC = () => {
  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>Autopack Dashboard</h1>
      <p style={{ color: '#666', marginBottom: '30px' }}>
        Autonomous Build System
      </p>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '20px',
        }}
      >
        <Link
          to="/runs"
          style={{
            display: 'block',
            padding: '25px',
            backgroundColor: '#f8f9fa',
            border: '1px solid #dee2e6',
            borderRadius: '8px',
            textDecoration: 'none',
            color: 'inherit',
            transition: 'box-shadow 0.2s',
          }}
        >
          <h2 style={{ marginBottom: '10px', color: '#007bff' }}>
            Runs Inbox
          </h2>
          <p style={{ color: '#666', margin: 0 }}>
            View all autonomous runs, monitor progress, and access artifacts.
          </p>
        </Link>

        <div
          style={{
            padding: '25px',
            backgroundColor: '#f8f9fa',
            border: '1px solid #dee2e6',
            borderRadius: '8px',
          }}
        >
          <h2 style={{ marginBottom: '10px', color: '#6c757d' }}>
            System Status
          </h2>
          <p style={{ color: '#666', margin: 0 }}>
            Monitor system health and resource usage.
          </p>
        </div>

        <div
          style={{
            padding: '25px',
            backgroundColor: '#f8f9fa',
            border: '1px solid #dee2e6',
            borderRadius: '8px',
          }}
        >
          <h2 style={{ marginBottom: '10px', color: '#6c757d' }}>
            Configuration
          </h2>
          <p style={{ color: '#666', margin: 0 }}>
            Manage build settings and automation policies.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
