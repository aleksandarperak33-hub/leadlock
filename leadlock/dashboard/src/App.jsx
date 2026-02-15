import { Routes, Route, Navigate } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import Dashboard from './pages/Dashboard';
import LeadFeed from './pages/LeadFeed';
import Conversations from './pages/Conversations';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import Login from './pages/Login';

function App() {
  const token = localStorage.getItem('ll_token');

  if (!token) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/leads" element={<LeadFeed />} />
        <Route path="/conversations/:leadId?" element={<Conversations />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="/login" element={<Login />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
