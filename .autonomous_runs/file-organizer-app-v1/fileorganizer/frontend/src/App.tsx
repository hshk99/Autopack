import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import PackSelection from './pages/PackSelection';
import Upload from './pages/Upload';
import TriageBoard from './pages/TriageBoard';
import Export from './pages/Export';
import Settings from './pages/Settings';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/packs" element={<PackSelection />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/triage" element={<TriageBoard />} />
          <Route path="/export" element={<Export />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
