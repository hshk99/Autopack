import React, { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

const Upload: React.FC = () => {
  const [searchParams] = useSearchParams();
  const packId = searchParams.get('pack');
  const navigate = useNavigate();

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string>('');

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      const files = Array.from(event.target.files);
      setSelectedFiles(prev => [...prev, ...files]);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const uploadFiles = async () => {
    if (selectedFiles.length === 0) return;

    setUploading(true);
    setUploadStatus('Uploading files...');

    try {
      // Upload each file
      for (const file of selectedFiles) {
        const formData = new FormData();
        formData.append('file', file);

        const uploadResponse = await axios.post(
          'http://127.0.0.1:8000/api/v1/documents/upload',
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' } }
        );

        const documentId = uploadResponse.data.id;

        // Trigger processing
        await axios.post(
          `http://127.0.0.1:8000/api/v1/documents/${documentId}/process`
        );
      }

      setUploadStatus(`[OK] ${selectedFiles.length} file(s) uploaded and processed`);

      // Navigate to triage board (Week 3 deliverable)
      setTimeout(() => {
        navigate(`/triage?pack=${packId}`);
      }, 2000);

    } catch (error) {
      console.error('Upload failed:', error);
      setUploadStatus('[ERROR] Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">
          Upload Documents
        </h1>
        <p className="text-gray-600 mb-8">
          Upload your documents for OCR and classification
        </p>

        {/* File input */}
        <div className="bg-white rounded-lg shadow-md p-8 mb-6">
          <label className="block mb-4">
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-12 text-center hover:border-blue-500 transition-colors cursor-pointer">
              <input
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={handleFileSelect}
                className="hidden"
              />
              <div className="text-gray-600">
                <p className="text-lg font-semibold mb-2">
                  Click to select files
                </p>
                <p className="text-sm">
                  Supported: PDF, PNG, JPG (max 50 MB each)
                </p>
              </div>
            </div>
          </label>

          {/* Selected files list */}
          {selectedFiles.length > 0 && (
            <div className="mt-6">
              <h3 className="font-semibold mb-3">Selected Files:</h3>
              <ul className="space-y-2">
                {selectedFiles.map((file, index) => (
                  <li
                    key={index}
                    className="flex justify-between items-center bg-gray-50 p-3 rounded"
                  >
                    <span className="text-sm text-gray-700">
                      {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                    </span>
                    <button
                      onClick={() => removeFile(index)}
                      className="text-red-500 hover:text-red-700 text-sm font-medium"
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Upload button */}
          <button
            onClick={uploadFiles}
            disabled={selectedFiles.length === 0 || uploading}
            className="w-full mt-6 bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {uploading ? 'Processing...' : `Upload ${selectedFiles.length} file(s)`}
          </button>

          {/* Status message */}
          {uploadStatus && (
            <p className="mt-4 text-center text-gray-700">{uploadStatus}</p>
          )}
        </div>

        {/* Back button */}
        <button
          onClick={() => navigate('/packs')}
          className="text-blue-600 hover:text-blue-700 font-medium"
        >
          <- Back to Pack Selection
        </button>
      </div>
    </div>
  );
};

export default Upload;
