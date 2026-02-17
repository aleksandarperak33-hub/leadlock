import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Users, MessageSquare, Calendar, BarChart3,
  Shield, Settings2, LogOut, Menu, X, Zap, ChevronLeft, ChevronRight,
  CreditCard, AlertTriangle, Mail,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Overview' },
  { to: '/leads', icon: Users, label: 'Leads' },
  { to: '/conversations', icon: MessageSquare, label: 'Conversations' },
  { to: '/bookings', icon: Calendar, label: 'Bookings' },
  { to: '/reports', icon: BarChart3, label: 'Reports' },
  { to: '/compliance', icon: Shield, label: 'Compliance' },
  { to: '/billing', icon: CreditCard, label: 'Billing' },
  { to: '/settings', icon: Settings2, label: 'Settings' },
];

function VerificationBanner() {
  const [dismissed, setDismissed] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  if (dismissed) return null;

  const handleResend = async () => {
    setSending(true);
    try {
      const token = localStorage.getItem('ll_token');
      await fetch('/api/v1/auth/resend-verification', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      setSent(true);
    } catch (err) {
      console.error('Failed to resend verification:', err);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="bg-amber-50 border border-amber-200/60 rounded-xl px-4 py-3 mb-6 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2.5 text-sm text-amber-700">
        <Mail className="w-4 h-4 flex-shrink-0" />
        <span>Please verify your email address to unlock all features.</span>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {sent ? (
          <span className="text-xs text-green-600 font-medium">Sent!</span>
        ) : (
          <button
            onClick={handleResend}
            disabled={sending}
            className="text-xs font-semibold text-amber-700 hover:text-amber-800 underline cursor-pointer disabled:opacity-50"
          >
            {sending ? 'Sending...' : 'Resend'}
          </button>
        )}
        <button onClick={() => setDismissed(true)} className="text-amber-400 hover:text-amber-600 cursor-pointer">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export default function DashboardLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [emailVerified, setEmailVerified] = useState(true); // assume verified until proven otherwise
  const [billingStatus, setBillingStatus] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();
  const businessName = localStorage.getItem('ll_business') || 'LeadLock';
  const initial = businessName.charAt(0).toUpperCase();

  // Check email verification and billing status on mount
  useEffect(() => {
    const token = localStorage.getItem('ll_token');
    if (!token) return;
    fetch('/api/v1/billing/status', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) setBillingStatus(data.billing_status);
      })
      .catch(() => {});
    // Check verification from settings
    fetch('/api/v1/dashboard/settings', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.email_verified === false) setEmailVerified(false);
      })
      .catch(() => {});
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('ll_token');
    localStorage.removeItem('ll_business');
    localStorage.removeItem('ll_is_admin');
    localStorage.removeItem('ll_client_id');
    window.location.href = '/login';
  };

  const isActive = (path) => location.pathname === path || location.pathname.startsWith(path + '/');

  const sidebarWidth = collapsed ? 'w-[72px]' : 'w-64';
  const contentMargin = collapsed ? 'lg:ml-[72px]' : 'lg:ml-64';

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex flex-col bg-white border-r border-gray-200/60 transition-all duration-300 ${sidebarWidth} ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-6">
          <div className="w-9 h-9 rounded-xl bg-orange-500 flex items-center justify-center flex-shrink-0">
            <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
          </div>
          {!collapsed && (
            <span className="text-lg font-semibold text-gray-900 truncate">
              LeadLock
            </span>
          )}
          {/* Mobile close */}
          <button
            onClick={() => setMobileOpen(false)}
            className="ml-auto lg:hidden text-gray-400 hover:text-gray-600 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-2 overflow-y-auto">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
            const active = isActive(to);

            return (
              <div key={to} className="relative group">
                <button
                  onClick={() => {
                    navigate(to);
                    setMobileOpen(false);
                  }}
                  className={`flex items-center gap-3 mx-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors cursor-pointer w-[calc(100%-24px)] ${
                    active
                      ? 'text-orange-600 bg-orange-50/80 border-l-2 border-orange-500'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <Icon className={`w-5 h-5 flex-shrink-0 ${active ? 'text-orange-600' : ''}`} />
                  {!collapsed && <span className="truncate">{label}</span>}
                </button>
                {/* Tooltip when collapsed */}
                {collapsed && (
                  <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2 py-1 bg-gray-900 text-white text-xs rounded-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50 hidden lg:block">
                    {label}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Bottom section */}
        <div className="border-t border-gray-200/60">
          {/* User info */}
          <div className="flex items-center gap-3 px-5 py-4">
            <div className="w-8 h-8 rounded-full bg-orange-100 text-orange-600 text-xs font-bold flex items-center justify-center flex-shrink-0">
              {initial}
            </div>
            {!collapsed && (
              <span className="text-sm font-medium text-gray-700 truncate">
                {businessName}
              </span>
            )}
          </div>

          {/* Sign out */}
          <div className="px-3 pb-2">
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 w-full px-3 py-2 rounded-xl text-sm font-medium text-gray-400 hover:text-red-500 hover:bg-gray-50 transition-colors cursor-pointer"
            >
              <LogOut className="w-5 h-5 flex-shrink-0" />
              {!collapsed && <span>Sign out</span>}
            </button>
          </div>

          {/* Collapse toggle */}
          <button
            onClick={() => setCollapsed((prev) => !prev)}
            className="hidden lg:flex w-full justify-center py-3 text-gray-400 hover:text-gray-600 cursor-pointer transition-colors border-t border-gray-200/60"
          >
            {collapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className={`transition-all duration-300 ${contentMargin}`}>
        {/* Mobile header */}
        <div className="lg:hidden flex items-center gap-3 px-4 h-14 sticky top-0 z-30 bg-white/90 backdrop-blur-sm border-b border-gray-200/60">
          <button
            onClick={() => setMobileOpen(true)}
            className="text-gray-500 cursor-pointer"
          >
            <Menu className="w-5 h-5" />
          </button>
          <span className="text-sm font-semibold text-gray-900">LeadLock</span>
        </div>

        <div className="max-w-[1400px] mx-auto px-8 py-8 min-h-screen">
          {!emailVerified && <VerificationBanner />}
          {billingStatus === 'past_due' && (
            <div className="bg-red-50 border border-red-200/60 rounded-xl px-4 py-3 mb-6 flex items-center gap-2.5 text-sm text-red-700">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>Your payment failed. <button onClick={() => navigate('/billing')} className="font-semibold underline cursor-pointer">Update payment method</button> to avoid service interruption.</span>
            </div>
          )}
          {billingStatus === 'trial' && (
            <div className="bg-orange-50 border border-orange-200/60 rounded-xl px-4 py-3 mb-6 flex items-center gap-2.5 text-sm text-orange-700">
              <Zap className="w-4 h-4 flex-shrink-0" />
              <span>You're on a free trial. <button onClick={() => navigate('/billing')} className="font-semibold underline cursor-pointer">Subscribe now</button> to keep your leads flowing.</span>
            </div>
          )}
          <Outlet />
        </div>
      </div>
    </div>
  );
}
