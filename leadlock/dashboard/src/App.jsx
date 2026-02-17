import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import AdminLayout from './layouts/AdminLayout';

// Loading fallback
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-3 border-orange-200 border-t-orange-500 rounded-full animate-spin" />
    </div>
  );
}

// Lazy-loaded pages — reduces initial bundle from ~1MB to ~200KB
const Dashboard = lazy(() => import('./pages/Dashboard'));
const LeadFeed = lazy(() => import('./pages/LeadFeed'));
const Conversations = lazy(() => import('./pages/Conversations'));
const Reports = lazy(() => import('./pages/Reports'));
const Settings = lazy(() => import('./pages/Settings'));
const Bookings = lazy(() => import('./pages/Bookings'));
const Compliance = lazy(() => import('./pages/Compliance'));
const Billing = lazy(() => import('./pages/Billing'));
const Login = lazy(() => import('./pages/Login'));
const Landing = lazy(() => import('./pages/Landing'));
const Signup = lazy(() => import('./pages/Signup'));
const Onboarding = lazy(() => import('./pages/Onboarding'));
const Privacy = lazy(() => import('./pages/Privacy'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const VerifyEmail = lazy(() => import('./pages/VerifyEmail'));

// Admin pages
const AdminCommandCenter = lazy(() => import('./pages/admin/AdminCommandCenter'));
const AdminOverview = lazy(() => import('./pages/admin/AdminOverview'));
const AdminClients = lazy(() => import('./pages/admin/AdminClients'));
const AdminClientDetail = lazy(() => import('./pages/admin/AdminClientDetail'));
const AdminLeads = lazy(() => import('./pages/admin/AdminLeads'));
const AdminRevenue = lazy(() => import('./pages/admin/AdminRevenue'));
const AdminOutreach = lazy(() => import('./pages/admin/AdminOutreach'));
const AdminSalesEngine = lazy(() => import('./pages/admin/AdminSalesEngine'));
const AdminCampaigns = lazy(() => import('./pages/admin/AdminCampaigns'));
const AdminCampaignDetail = lazy(() => import('./pages/admin/AdminCampaignDetail'));
const AdminInbox = lazy(() => import('./pages/admin/AdminInbox'));
const AdminInsights = lazy(() => import('./pages/admin/AdminInsights'));
const AdminTemplates = lazy(() => import('./pages/admin/AdminTemplates'));

function App() {
  const token = localStorage.getItem('ll_token');
  const isAdmin = localStorage.getItem('ll_is_admin') === 'true';

  if (!token) {
    return (
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    );
  }

  if (isAdmin) {
    return (
      <Suspense fallback={<PageLoader />}>
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
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/leads" element={<LeadFeed />} />
          <Route path="/conversations/:leadId?" element={<Conversations />} />
          <Route path="/bookings" element={<Bookings />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/billing" element={<Billing />} />
        </Route>
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
