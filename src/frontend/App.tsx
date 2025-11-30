/**
 * Root application component
 * 
 * Sets up routing and global layout structure
 */
import { Routes, Route } from 'react-router-dom';
import Dashboard from '@pages/Dashboard';
import BuildView from '@pages/BuildView';
import NotFound from '@pages/NotFound';

function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/builds/:buildId" element={<BuildView />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

export default App;
