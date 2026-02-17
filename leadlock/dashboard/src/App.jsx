import { Routes, Route, Navigate } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import AdminLayout from './layouts/AdminLayout';
import Dashboard from './pages/Dashboard';
import LeadFeed from './pages/LeadFeed';
import Conversations from './pages/Conversations';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import Bookings from './pages/Bookings';
import Compliance from './pages/Compliance';
import Login from './pages/Login';
import Landing from './pages/Landing';
import Signup from './pages/Signup';
import Onboarding from './pages/Onboarding';
import Privacy from './pages/Privacy';
import AdminCommandCenter from './pages/admin/AdminCommandCenter';
import AdminOverview from './pages/admin/AdminOverview';
import AdminClients from './pages/admin/AdminClients';
import AdminClientDetail from './pages/admin/AdminClientDetail';
import AdminLeads from './pages/admin/AdminLeads';
import AdminRevenue from './pages/admin/AdminRevenue';
import AdminOutreach from './pages/admin/AdminOutreach';
import AdminSalesEngine from './pages/admin/AdminSalesEngine';
import AdminCampaigns from './pages/admin/AdminCampaigns';
import AdminCampaignDetail from './pages/admin/AdminCampaignDetail';
import AdminInbox from './pages/admin/AdminInbox';
import AdminInsights from './pages/admin/AdminInsights';
import AdminTemplates from './pages/admin/AdminTemplates';

function App() {
  const token = localStorage.getItem('ll_token');
  const isAdmin = localStorage.getItem('ll_is_admin') === 'true';

  if (!token) {
    return (
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    );
  }

  if (isAdmin) {
    return (
      <Routes>
        <Route element={<AdminLayout />}>
          <Route path="/dashboard" element={<AdminCommandCenter />} />
          <Route path="/overview" element={<AdminOverview />} />
          <Route path="/clients" element={<AdminClients />} />
          <Route path="/clients/:clientId" element={<AdminClientDetail />} />
          <Route path="/leads" element={<AdminLeads />} />
          <Route path="/revenue" element={<AdminRevenue />} />
          <Route path="/outreach" element={<AdminOutreach />} />
          <Route path="/sales-engine" element={<AdminSalesEngine />} />
          <Route path="/campaigns" element={<AdminCampaigns />} />
          <Route path="/campaigns/:campaignId" element={<AdminCampaignDetail />} />
          <Route path="/inbox" element={<AdminInbox />} />
          <Route path="/insights" element={<AdminInsights />} />
          <Route path="/templates" element={<AdminTemplates />} />
        </Route>
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/onboarding" element={<Onboarding />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route element={<DashboardLayout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/leads" element={<LeadFeed />} />
        <Route path="/conversations/:leadId?" element={<Conversations />} />
        <Route path="/bookings" element={<Bookings />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/compliance" element={<Compliance />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="/login" element={<Navigate to="/dashboard" replace />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default App;
