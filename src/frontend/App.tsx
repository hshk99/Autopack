/**
 * Root application component
 *
 * Sets up routing and global layout structure
 *
 * GAP-8.10.x UI operator-surface upgrades:
 * - /runs: Multi-run inbox view (GAP-8.10.2)
 * - /builds/:buildId/artifacts: Artifacts panel (GAP-8.10.1)
 * - /builds/:buildId/browser-artifacts: Browser artifacts viewer (GAP-8.10.3)
 * - /builds/:buildId/progress: Enhanced progress visualization (GAP-8.10.4)
 */
import { Routes, Route } from 'react-router-dom';
import Dashboard from '@pages/Dashboard';
import BuildView from '@pages/BuildView';
import NotFound from '@pages/NotFound';
import RunsInbox from '@pages/RunsInbox';
import Artifacts from '@pages/Artifacts';
import BrowserArtifacts from '@pages/BrowserArtifacts';
import ProgressView from '@pages/ProgressView';

function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/runs" element={<RunsInbox />} />
        <Route path="/builds/:buildId" element={<BuildView />} />
        <Route path="/builds/:buildId/artifacts" element={<Artifacts />} />
        <Route path="/builds/:buildId/browser-artifacts" element={<BrowserArtifacts />} />
        <Route path="/builds/:buildId/progress" element={<ProgressView />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

export default App;
