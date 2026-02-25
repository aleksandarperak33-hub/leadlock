import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import DashboardLayout from './layouts/DashboardLayout';
import AdminLayout from './layouts/AdminLayout';
import PageErrorBoundary from './components/PageErrorBoundary';

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-3 border-orange-200 border-t-orange-500 rounded-full animate-spin" />
    </div>
  );
}

/**
 * Wraps a lazy page component with Suspense + per-page error boundary.
 */
function Page({ component: Component }) {
  return (
    <PageErrorBoundary>
      <Suspense fallback={<PageLoader />}>
        <Component />
      </Suspense>
    </PageErrorBoundary>
  );
}

// Lazy-loaded pages
const Dashboard = lazy(() => import('./pages/Dashboard'));
const LeadFeed = lazy(() => import('./pages/LeadFeed'));
const Conversations = lazy(() => import('./pages/Conversations'));
const Reports = lazy(() => import('./pages/Reports'));
const ROI = lazy(() => import('./pages/ROI'));
const Settings = lazy(() => import('./pages/Settings'));
const Bookings = lazy(() => import('./pages/Bookings'));
const Compliance = lazy(() => import('./pages/Compliance'));
const Billing = lazy(() => import('./pages/Billing'));
const Login = lazy(() => import('./pages/Login'));
const Landing = lazy(() => import('./pages/Landing'));
const Signup = lazy(() => import('./pages/Signup'));
const Onboarding = lazy(() => import('./pages/Onboarding'));
const Privacy = lazy(() => import('./pages/Privacy'));
const Terms = lazy(() => import('./pages/Terms'));
const About = lazy(() => import('./pages/About'));
const Contact = lazy(() => import('./pages/Contact'));
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
const AdminAnalytics = lazy(() => import('./pages/admin/AdminAnalytics'));
const AdminAgents = lazy(() => import('./pages/admin/AdminAgents'));

function App() {
  const { token, isAdmin } = useAuth();

  if (!token) {
    return (
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Page component={Landing} />} />
          <Route path="/login" element={<Page component={Login} />} />
          <Route path="/signup" element={<Page component={Signup} />} />
          <Route path="/onboarding" element={<Page component={Onboarding} />} />
          <Route path="/privacy" element={<Page component={Privacy} />} />
          <Route path="/terms" element={<Page component={Terms} />} />
          <Route path="/about" element={<Page component={About} />} />
          <Route path="/contact" element={<Page component={Contact} />} />
          <Route path="/forgot-password" element={<Page component={ForgotPassword} />} />
          <Route path="/reset-password" element={<Page component={ResetPassword} />} />
          <Route path="/verify-email" element={<Page component={VerifyEmail} />} />
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
            <Route path="/dashboard" element={<Page component={AdminCommandCenter} />} />
            <Route path="/overview" element={<Page component={AdminOverview} />} />
            <Route path="/clients" element={<Page component={AdminClients} />} />
            <Route path="/clients/:clientId" element={<Page component={AdminClientDetail} />} />
            <Route path="/leads" element={<Page component={AdminLeads} />} />
            <Route path="/revenue" element={<Page component={AdminRevenue} />} />
            <Route path="/outreach" element={<Page component={AdminOutreach} />} />
            <Route path="/sales-engine" element={<Page component={AdminSalesEngine} />} />
            <Route path="/campaigns" element={<Page component={AdminCampaigns} />} />
            <Route path="/campaigns/:campaignId" element={<Page component={AdminCampaignDetail} />} />
            <Route path="/inbox" element={<Page component={AdminInbox} />} />
            <Route path="/insights" element={<Page component={AdminInsights} />} />
            <Route path="/templates" element={<Page component={AdminTemplates} />} />
            <Route path="/analytics" element={<Page component={AdminAnalytics} />} />
            <Route path="/agents" element={<Page component={AdminAgents} />} />
          </Route>
          <Route path="/privacy" element={<Page component={Privacy} />} />
          <Route path="/terms" element={<Page component={Terms} />} />
          <Route path="/about" element={<Page component={About} />} />
          <Route path="/contact" element={<Page component={Contact} />} />
          <Route path="/login" element={<Navigate to="/dashboard" replace />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
    );
  }

  // Check if onboarding is incomplete — redirect to onboarding
  const onboardingStatus = localStorage.getItem('ll_onboarding_status');
  if (onboardingStatus && onboardingStatus !== 'live') {
    return (
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/onboarding" element={<Page component={Onboarding} />} />
          <Route path="/privacy" element={<Page component={Privacy} />} />
          <Route path="/terms" element={<Page component={Terms} />} />
          <Route path="/about" element={<Page component={About} />} />
          <Route path="/contact" element={<Page component={Contact} />} />
          <Route path="/verify-email" element={<Page component={VerifyEmail} />} />
          <Route path="/billing" element={<Page component={Billing} />} />
          <Route path="*" element={<Navigate to="/onboarding" replace />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/onboarding" element={<Page component={Onboarding} />} />
        <Route path="/privacy" element={<Page component={Privacy} />} />
        <Route path="/terms" element={<Page component={Terms} />} />
        <Route path="/verify-email" element={<Page component={VerifyEmail} />} />
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<Page component={Dashboard} />} />
          <Route path="/leads" element={<Page component={LeadFeed} />} />
          <Route path="/conversations/:leadId?" element={<Page component={Conversations} />} />
          <Route path="/bookings" element={<Page component={Bookings} />} />
          <Route path="/reports" element={<Page component={Reports} />} />
          <Route path="/roi" element={<Page component={ROI} />} />
          <Route path="/compliance" element={<Page component={Compliance} />} />
          <Route path="/settings" element={<Page component={Settings} />} />
          <Route path="/billing" element={<Page component={Billing} />} />
        </Route>
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
