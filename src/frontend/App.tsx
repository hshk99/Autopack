/**
 * Root application component
 *
 * Sets up routing and global layout structure
 */
import { Routes, Route } from 'react-router-dom';
import Dashboard from '@pages/Dashboard';
import BuildView from '@pages/BuildView';
import NotFound from '@pages/NotFound';
import RunsInbox from '@pages/RunsInbox';
import RunArtifacts from '@pages/RunArtifacts';
import RunBrowserArtifacts from '@pages/RunBrowserArtifacts';
import RunProgress from '@pages/RunProgress';
import Metrics from '@pages/Metrics';

function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/builds/:buildId" element={<BuildView />} />
        {/* GAP-8.10 Operator Surface routes */}
        <Route path="/runs" element={<RunsInbox />} />
        <Route path="/runs/:runId/artifacts" element={<RunArtifacts />} />
        <Route path="/runs/:runId/browser" element={<RunBrowserArtifacts />} />
        <Route path="/runs/:runId/progress" element={<RunProgress />} />
        {/* IMP-TELE-010: Pipeline Health Dashboard */}
        <Route path="/metrics" element={<Metrics />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

export default App;
