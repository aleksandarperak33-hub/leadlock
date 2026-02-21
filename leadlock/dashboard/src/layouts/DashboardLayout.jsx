import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Users, MessageSquare, Calendar, BarChart3,
  Shield, Settings2, CreditCard, AlertTriangle, Mail, X, Zap,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import BaseLayout from './BaseLayout';

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
  const { token } = useAuth();

  if (dismissed) return null;

  const handleResend = async () => {
    setSending(true);
    try {
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
        <button onClick={() => setDismissed(true)} className="text-amber-400 hover:text-amber-600 cursor-pointer" aria-label="Dismiss">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export default function DashboardLayout() {
  const { token, businessName, initial, logout } = useAuth();
  const navigate = useNavigate();
  const [emailVerified, setEmailVerified] = useState(true);
  const [billingStatus, setBillingStatus] = useState(null);

  useEffect(() => {
    if (!token) return;
    fetch('/api/v1/billing/status', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setBillingStatus(data.billing_status); })
      .catch(() => {});
    fetch('/api/v1/dashboard/settings', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data && data.email_verified === false) setEmailVerified(false); })
      .catch(() => {});
  }, [token]);

  const banners = (
    <>
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
    </>
  );

  return (
    <BaseLayout
      navItems={NAV_ITEMS}
      userInitial={initial}
      userName={businessName}
      banners={banners}
      onLogout={logout}
    />
  );
}
