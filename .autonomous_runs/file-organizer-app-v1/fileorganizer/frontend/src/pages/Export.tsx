import React, { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

type ExportFormat = 'pdf' | 'excel' | 'csv';

const Export: React.FC = () => {
  const [searchParams] = useSearchParams();
  const packId = searchParams.get('pack');
  const navigate = useNavigate();

  const [selectedFormat, setSelectedFormat] = useState<ExportFormat>('pdf');
  const [exporting, setExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState<string>('');

  const handleExport = async () => {
    if (!packId) {
      alert('No pack selected');
      return;
    }

    setExporting(true);
    setExportStatus('Generating export...');

    try {
      // Determine export endpoint
      const endpoints: Record<ExportFormat, string> = {
        pdf: `/api/v1/export/pdf/${packId}`,
        excel: `/api/v1/export/excel/${packId}`,
        csv: `/api/v1/export/csv/${packId}`,
      };

      const endpoint = endpoints[selectedFormat];

      // Download file
      const response = await fetch(`http://127.0.0.1:8000${endpoint}`);

      if (!response.ok) {
        throw new Error('Export failed');
      }

      // Get filename from Content-Disposition header
      const contentDisposition = response.headers.get('content-disposition');
      let filename = `export.${selectedFormat === 'excel' ? 'xlsx' : selectedFormat}`;

      if (contentDisposition) {
        const match = contentDisposition.match(/filename="(.+)"/);
        if (match) {
          filename = match[1];
        }
      }

      // Create blob and download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setExportStatus(`[OK] Export successful: ${filename}`);

      // Navigate back after 2 seconds
      setTimeout(() => {
        navigate(`/triage?pack=${packId}`);
      }, 2000);

    } catch (error) {
      console.error('Export failed:', error);
      setExportStatus('[ERROR] Export failed. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">
          Export Document Pack
        </h1>
        <p className="text-gray-600 mb-8">
          Choose export format and download your organized documents
        </p>

        <div className="bg-white rounded-lg shadow-md p-8">
          <h2 className="text-xl font-semibold mb-4">Select Export Format</h2>

          <div className="space-y-4 mb-8">
            {/* PDF option */}
            <div
              onClick={() => setSelectedFormat('pdf')}
              className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
                selectedFormat === 'pdf'
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="flex items-center">
                <input
                  type="radio"
                  checked={selectedFormat === 'pdf'}
                  onChange={() => setSelectedFormat('pdf')}
                  className="mr-3"
                />
                <div>
                  <h3 className="font-semibold text-gray-800">PDF Document</h3>
                  <p className="text-sm text-gray-600">
                    Professional report with categorized document lists
                  </p>
                </div>
              </div>
            </div>

            {/* Excel option */}
            <div
              onClick={() => setSelectedFormat('excel')}
              className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
                selectedFormat === 'excel'
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="flex items-center">
                <input
                  type="radio"
                  checked={selectedFormat === 'excel'}
                  onChange={() => setSelectedFormat('excel')}
                  className="mr-3"
                />
                <div>
                  <h3 className="font-semibold text-gray-800">Excel Workbook</h3>
                  <p className="text-sm text-gray-600">
                    Spreadsheet with summary and category sheets
                  </p>
                </div>
              </div>
            </div>

            {/* CSV option */}
            <div
              onClick={() => setSelectedFormat('csv')}
              className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
                selectedFormat === 'csv'
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="flex items-center">
                <input
                  type="radio"
                  checked={selectedFormat === 'csv'}
                  onChange={() => setSelectedFormat('csv')}
                  className="mr-3"
                />
                <div>
                  <h3 className="font-semibold text-gray-800">CSV File</h3>
                  <p className="text-sm text-gray-600">
                    Simple comma-separated values for data import
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Export button */}
          <button
            onClick={handleExport}
            disabled={exporting}
            className="w-full bg-green-600 text-white py-3 rounded-lg font-semibold hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {exporting ? 'Exporting...' : `Export as ${selectedFormat.toUpperCase()}`}
          </button>

          {/* Status message */}
          {exportStatus && (
            <p className="mt-4 text-center text-gray-700">{exportStatus}</p>
          )}
        </div>

        {/* Back button */}
        <button
          onClick={() => navigate(`/triage?pack=${packId}`)}
          className="mt-6 text-blue-600 hover:text-blue-700 font-medium"
        >
          <- Back to Triage Board
        </button>

        <div className="mt-12 text-center text-gray-500">
          <p className="text-sm">Week 5: Export Engines (PDF/Excel/CSV)</p>
        </div>
      </div>
    </div>
  );
};

export default Export;
