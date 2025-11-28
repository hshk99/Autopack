import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

interface AppSettings {
  apiKey: string;
  tesseractPath: string;
  maxFileSize: number;
  autoClassify: boolean;
  confidenceThreshold: number;
}

const Settings: React.FC = () => {
  const navigate = useNavigate();

  const [settings, setSettings] = useState<AppSettings>({
    apiKey: '',
    tesseractPath: '',
    maxFileSize: 50,
    autoClassify: true,
    confidenceThreshold: 80,
  });

  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string>('');

  // Load settings from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('fileorganizer_settings');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setSettings(parsed);
      } catch (e) {
        console.error('Failed to load settings:', e);
      }
    }
  }, []);

  const handleSave = () => {
    setSaving(true);
    setSaveStatus('Saving...');

    try {
      // Save to localStorage
      localStorage.setItem('fileorganizer_settings', JSON.stringify(settings));

      setSaveStatus('[OK] Settings saved successfully');

      setTimeout(() => {
        setSaveStatus('');
      }, 3000);

    } catch (error) {
      console.error('Failed to save settings:', error);
      setSaveStatus('[ERROR] Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (confirm('Are you sure you want to reset all settings to defaults?')) {
      const defaults: AppSettings = {
        apiKey: '',
        tesseractPath: '',
        maxFileSize: 50,
        autoClassify: true,
        confidenceThreshold: 80,
      };
      setSettings(defaults);
      localStorage.removeItem('fileorganizer_settings');
      setSaveStatus('[OK] Settings reset to defaults');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">
          Settings
        </h1>
        <p className="text-gray-600 mb-8">
          Configure FileOrganizer application settings
        </p>

        <div className="bg-white rounded-lg shadow-md p-8 space-y-6">
          {/* API Configuration */}
          <div>
            <h2 className="text-xl font-semibold mb-4">API Configuration</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  OpenAI API Key
                </label>
                <input
                  type="password"
                  value={settings.apiKey}
                  onChange={(e) => setSettings({...settings, apiKey: e.target.value})}
                  placeholder="sk-..."
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Required for AI classification. Get your key at openai.com
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Tesseract OCR Path (Optional)
                </label>
                <input
                  type="text"
                  value={settings.tesseractPath}
                  onChange={(e) => setSettings({...settings, tesseractPath: e.target.value})}
                  placeholder="Auto-detected if blank"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Path to Tesseract executable (auto-detected if not set)
                </p>
              </div>
            </div>
          </div>

          {/* Processing Settings */}
          <div className="border-t pt-6">
            <h2 className="text-xl font-semibold mb-4">Processing Settings</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Maximum File Size (MB)
                </label>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={settings.maxFileSize}
                  onChange={(e) => setSettings({...settings, maxFileSize: parseInt(e.target.value)})}
                  className="w-32 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Maximum allowed file size for uploads
                </p>
              </div>

              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.autoClassify}
                    onChange={(e) => setSettings({...settings, autoClassify: e.target.checked})}
                    className="mr-2"
                  />
                  <span className="text-sm font-medium text-gray-700">
                    Auto-classify documents after upload
                  </span>
                </label>
                <p className="text-xs text-gray-500 mt-1 ml-6">
                  Automatically run AI classification after OCR completes
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Confidence Threshold for Review (%)
                </label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={settings.confidenceThreshold}
                  onChange={(e) => setSettings({...settings, confidenceThreshold: parseInt(e.target.value)})}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>0%</span>
                  <span className="font-semibold">{settings.confidenceThreshold}%</span>
                  <span>100%</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  Documents below this threshold will be flagged for review
                </p>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="border-t pt-6 flex justify-between">
            <button
              onClick={handleReset}
              className="px-6 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium"
            >
              Reset to Defaults
            </button>

            <button
              onClick={handleSave}
              disabled={saving}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 font-medium"
            >
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>

          {/* Status message */}
          {saveStatus && (
            <p className="text-center text-gray-700 font-medium">{saveStatus}</p>
          )}
        </div>

        {/* Navigation */}
        <button
          onClick={() => navigate('/')}
          className="mt-6 text-blue-600 hover:text-blue-700 font-medium"
        >
          <- Back to Home
        </button>

        <div className="mt-12 text-center text-gray-500">
          <p className="text-sm">FileOrganizer v1.0 - Week 7</p>
        </div>
      </div>
    </div>
  );
};

export default Settings;
