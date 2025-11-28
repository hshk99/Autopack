import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

interface Document {
  id: number;
  filename: string;
  assigned_category_id: number | null;
  classification_confidence: number | null;
  status: string;
}

interface Category {
  id: number;
  name: string;
  description: string;
}

type FilterType = 'all' | 'needs_review' | 'approved';

const TriageBoard: React.FC = () => {
  const [searchParams] = useSearchParams();
  const packId = searchParams.get('pack');
  const navigate = useNavigate();

  const [documents, setDocuments] = useState<Document[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [filter, setFilter] = useState<FilterType>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [editingDocId, setEditingDocId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [packId]);

  const loadData = async () => {
    try {
      const docsResponse = await axios.get('http://127.0.0.1:8000/api/v1/documents');
      setDocuments(docsResponse.data);

      if (packId) {
        const catsResponse = await axios.get(
          `http://127.0.0.1:8000/api/v1/packs/${packId}/categories`
        );
        setCategories(catsResponse.data);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getCategoryName = (categoryId: number | null): string => {
    if (!categoryId) return '(Uncategorized)';
    const category = categories.find(c => c.id === categoryId);
    return category ? category.name : 'Unknown';
  };

  const getConfidenceClass = (confidence: number | null): string => {
    if (!confidence) return 'text-gray-400';
    if (confidence >= 80) return 'text-green-600';
    if (confidence >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  const needsReview = (doc: Document): boolean => {
    return !doc.classification_confidence || doc.classification_confidence < 80;
  };

  const updateCategory = async (docId: number, categoryId: number) => {
    try {
      await axios.patch(
        `http://127.0.0.1:8000/api/v1/documents/${docId}/category`,
        { category_id: categoryId }
      );

      // Refresh documents
      await loadData();
      setEditingDocId(null);
    } catch (error) {
      console.error('Failed to update category:', error);
      alert('Failed to update category');
    }
  };

  const approveDocument = async (docId: number) => {
    try {
      await axios.post(
        `http://127.0.0.1:8000/api/v1/documents/${docId}/approve`,
        { approved: true }
      );

      // Refresh documents
      await loadData();
    } catch (error) {
      console.error('Failed to approve document:', error);
      alert('Failed to approve document');
    }
  };

  const filteredDocuments = documents.filter(doc => {
    // Apply filter
    if (filter === 'needs_review' && !needsReview(doc)) return false;
    if (filter === 'approved' && needsReview(doc)) return false;

    // Apply search
    if (searchTerm && !doc.filename.toLowerCase().includes(searchTerm.toLowerCase())) {
      return false;
    }

    return true;
  });

  const exportPack = () => {
    navigate(`/export?pack=${packId}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-lg text-gray-600">Loading triage board...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-800 mb-2">
              Triage Board
            </h1>
            <p className="text-gray-600">
              Review and organize classified documents
            </p>
          </div>

          <button
            onClick={exportPack}
            className="bg-green-600 text-white px-6 py-2 rounded-lg font-semibold hover:bg-green-700"
          >
            Export Pack
          </button>
        </div>

        {/* Search bar */}
        <div className="bg-white rounded-lg shadow-md p-4 mb-4">
          <input
            type="text"
            placeholder="Search by filename..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Filters */}
        <div className="bg-white rounded-lg shadow-md p-4 mb-6">
          <div className="flex items-center space-x-4">
            <span className="text-gray-700 font-medium">Filter:</span>
            <button
              onClick={() => setFilter('all')}
              className={`px-4 py-2 rounded ${
                filter === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              All ({documents.length})
            </button>
            <button
              onClick={() => setFilter('needs_review')}
              className={`px-4 py-2 rounded ${
                filter === 'needs_review'
                  ? 'bg-yellow-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Needs Review ({documents.filter(needsReview).length})
            </button>
            <button
              onClick={() => setFilter('approved')}
              className={`px-4 py-2 rounded ${
                filter === 'approved'
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Approved ({documents.filter(d => !needsReview(d)).length})
            </button>
          </div>
        </div>

        {/* Documents table */}
        <div className="bg-white rounded-lg shadow-md overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-100 border-b">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                  File Name
                </th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                  Category
                </th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                  Confidence
                </th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredDocuments.map(doc => (
                <tr key={doc.id} className="border-b hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm text-gray-800">
                    {doc.filename}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    {editingDocId === doc.id ? (
                      <select
                        className="border border-gray-300 rounded px-2 py-1"
                        defaultValue={doc.assigned_category_id || ''}
                        onChange={(e) => updateCategory(doc.id, Number(e.target.value))}
                        onBlur={() => setEditingDocId(null)}
                        autoFocus
                      >
                        <option value="">Select category...</option>
                        {categories.map(cat => (
                          <option key={cat.id} value={cat.id}>
                            {cat.name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span
                        onClick={() => setEditingDocId(doc.id)}
                        className="cursor-pointer hover:text-blue-600"
                      >
                        {getCategoryName(doc.assigned_category_id)}
                      </span>
                    )}
                  </td>
                  <td className={`px-6 py-4 text-sm font-semibold ${getConfidenceClass(doc.classification_confidence)}`}>
                    {doc.classification_confidence
                      ? `${doc.classification_confidence.toFixed(0)}%`
                      : 'N/A'}
                    {needsReview(doc) && <span className="ml-2">[WARNING]</span>}
                  </td>
                  <td className="px-6 py-4 text-sm space-x-2">
                    <button
                      onClick={() => approveDocument(doc.id)}
                      className="text-green-600 hover:text-green-700 font-medium"
                    >
                      [x] Approve
                    </button>
                    <button
                      onClick={() => setEditingDocId(doc.id)}
                      className="text-blue-600 hover:text-blue-700 font-medium"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredDocuments.length === 0 && (
            <div className="text-center py-12 text-gray-500">
              No documents to display
            </div>
          )}
        </div>

        <div className="mt-8 text-center text-gray-500">
          <p className="text-sm">Week 4: Triage Board Edit & Approve Functionality</p>
          <p className="text-sm">Total: {filteredDocuments.length} document(s)</p>
        </div>
      </div>
    </div>
  );
};

export default TriageBoard;
