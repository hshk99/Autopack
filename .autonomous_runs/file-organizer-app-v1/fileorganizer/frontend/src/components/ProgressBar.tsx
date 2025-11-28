import React from 'react';

interface ProgressBarProps {
  current: number;
  total: number;
  label?: string;
}

const ProgressBar: React.FC<ProgressBarProps> = ({ current, total, label }) => {
  const percentage = total > 0 ? Math.round((current / total) * 100) : 0;

  return (
    <div className="w-full">
      {label && (
        <div className="flex justify-between mb-2">
          <span className="text-sm text-gray-600">{label}</span>
          <span className="text-sm text-gray-600">{current} / {total}</span>
        </div>
      )}
      <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
        <div
          className="bg-blue-600 h-full transition-all duration-300 ease-out"
          style={{ width: `${percentage}%` }}
        >
          <span className="flex items-center justify-center h-full text-xs text-white font-semibold">
            {percentage}%
          </span>
        </div>
      </div>
    </div>
  );
};

export default ProgressBar;
