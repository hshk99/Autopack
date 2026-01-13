/**
 * Build view page component
 *
 * Displays detailed information about a specific build
 */
import React from 'react';
import { useParams } from 'react-router-dom';

const BuildView: React.FC = () => {
  const { buildId } = useParams<{ buildId: string }>();

  return (
    <div>
      <h1>Build View</h1>
      <p>Build ID: {buildId}</p>
    </div>
  );
};

export default BuildView;
