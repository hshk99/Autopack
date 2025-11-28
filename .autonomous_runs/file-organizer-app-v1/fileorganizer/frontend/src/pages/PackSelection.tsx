import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

interface Pack {
  id: number;
  name: string;
  description: string;
}

const PackSelection: React.FC = () => {
  const [packs, setPacks] = useState<Pack[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadPacks();
  }, []);

  const loadPacks = async () => {
    try {
      const response = await axios.get('http://127.0.0.1:8000/api/v1/packs');
      setPacks(response.data);
    } catch (error) {
      console.error('Failed to load packs:', error);
    } finally {
      setLoading(false);
    }
  };

  const selectPack = (packId: number) => {
    // Navigate to upload page with selected pack
    navigate(`/upload?pack=${packId}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-lg text-gray-600">Loading packs...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">
          Select Document Pack
        </h1>
        <p className="text-gray-600 mb-8">
          Choose the type of documents you want to organize
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {packs.map(pack => (
            <div
              key={pack.id}
              onClick={() => selectPack(pack.id)}
              className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer border-2 border-transparent hover:border-blue-500"
            >
              <h2 className="text-xl font-semibold text-gray-800 mb-2">
                {pack.name}
              </h2>
              <p className="text-gray-600">
                {pack.description || 'No description available'}
              </p>
            </div>
          ))}
        </div>

        {packs.length === 0 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
            <p className="text-yellow-800">
              No scenario packs available. Please load pack templates.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default PackSelection;
