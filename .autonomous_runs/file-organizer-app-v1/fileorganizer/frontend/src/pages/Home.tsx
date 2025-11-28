import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const Home: React.FC = () => {
  const [backendStatus, setBackendStatus] = useState<string>('Checking...');
  const navigate = useNavigate();

  useEffect(() => {
    axios.get('http://127.0.0.1:8000/api/v1/health')
      .then(response => {
        setBackendStatus(`[OK] ${response.data.service} - ${response.data.status}`);
      })
      .catch(error => {
        setBackendStatus('[ERROR] Backend not connected');
        console.error('Backend error:', error);
      });
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8">
      <h1 className="text-4xl font-bold text-gray-800 mb-4">
        FileOrganizer
      </h1>
      <p className="text-lg text-gray-600 mb-8">
        Intelligent Document Organization
      </p>

      <div className="bg-white rounded-lg shadow-md p-6 mb-8">
        <h2 className="text-xl font-semibold mb-4">Backend Status</h2>
        <p className="text-gray-700">{backendStatus}</p>
      </div>

      <button
        onClick={() => navigate('/packs')}
        className="bg-blue-600 text-white px-8 py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
      >
        Get Started
      </button>

      <div className="mt-12 text-center text-gray-500">
        <p className="text-sm">Week 2: OCR + Pack Selection + Upload UI</p>
      </div>
    </div>
  );
};

export default Home;
