import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CreditCard, Check, AlertCircle, ExternalLink, Zap } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';

const PLANS = [
  { slug: 'starter', name: 'Starter', price: '$297', priceId: '__STARTER__' },
  { slug: 'pro', name: 'Professional', price: '$597', priceId: '__PRO__', popular: true },
  { slug: 'business', name: 'Business', price: '$1,497', priceId: '__BUSINESS__' },
];

export default function Billing() {
  const [searchParams] = useSearchParams();
  const [billing, setBilling] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState('');
  const [error, setError] = useState('');
  const justSubscribed = searchParams.get('success') === 'true';
  const canceled = searchParams.get('canceled') === 'true';

  useEffect(() => {
    fetchBilling();
  }, []);

  const fetchBilling = async () => {
    try {
      const token = localStorage.getItem('ll_token');
      const res = await fetch('/api/v1/billing/status', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to load billing');
      const data = await res.json();
      setBilling(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCheckout = async (priceId) => {
    setActionLoading(priceId);
    setError('');
    try {
      const token = localStorage.getItem('ll_token');
      const res = await fetch('/api/v1/billing/create-checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ price_id: priceId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Checkout failed');
      window.location.href = data.url;
    } catch (e) {
      setError(e.message);
    } finally {
      setActionLoading('');
    }
  };

  const handlePortal = async () => {
    setActionLoading('portal');
    setError('');
    try {
      const token = localStorage.getItem('ll_token');
      const res = await fetch('/api/v1/billing/portal', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Portal failed');
      window.location.href = data.url;
    } catch (e) {
      setError(e.message);
    } finally {
      setActionLoading('');
    }
  };

  if (loading) {
    return (
      <div>
        <PageHeader title="Billing" />
        <div className="h-64 rounded-xl bg-gray-100 animate-pulse" />
      </div>
    );
  }

  const isActive = billing?.billing_status === 'active';
  const isTrial = billing?.billing_status === 'trial';
  const isPastDue = billing?.billing_status === 'past_due';

  return (
    <div>
      <PageHeader
        title="Billing"
        subtitle="Manage your subscription and payment method"
      />

      {/* Status banners */}
      {justSubscribed && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-green-50 border border-green-200/60 text-green-700 text-sm flex items-center gap-2">
          <Check className="w-4 h-4" />
          Subscription activated successfully! Welcome to LeadLock.
        </div>
      )}

      {canceled && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200/60 text-amber-700 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          Checkout was canceled. You can try again anytime.
        </div>
      )}

      {isPastDue && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-red-700 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          Your payment failed. Please update your payment method to avoid service interruption.
        </div>
      )}

      {error && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-red-600 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Current plan */}
      <div className="bg-white border border-gray-200/60 rounded-2xl p-6 mb-8">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <CreditCard className="w-5 h-5 text-gray-400" />
              <h2 className="text-base font-semibold text-gray-900">Current Plan</h2>
            </div>
            <div className="flex items-center gap-3 mt-2">
              <span className="text-2xl font-bold text-gray-900 capitalize">
                {billing?.plan !== 'none' ? billing?.plan : isTrial ? 'Free Trial' : 'No Plan'}
              </span>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                isActive ? 'bg-green-50 text-green-600' :
                isTrial ? 'bg-orange-50 text-orange-600' :
                isPastDue ? 'bg-red-50 text-red-600' :
                'bg-gray-100 text-gray-500'
              }`}>
                {billing?.billing_status?.replace('_', ' ')}
              </span>
            </div>
            {billing?.current_period_end && (
              <p className="text-xs text-gray-400 mt-1">
                Renews {new Date(billing.current_period_end * 1000).toLocaleDateString()}
              </p>
            )}
          </div>
          {(isActive || isPastDue) && (
            <button
              onClick={handlePortal}
              disabled={actionLoading === 'portal'}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium text-gray-700 border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer disabled:opacity-50"
            >
              <ExternalLink className="w-4 h-4" />
              {actionLoading === 'portal' ? 'Loading...' : 'Manage Subscription'}
            </button>
          )}
        </div>
      </div>

      {/* Plan selection */}
      {(!isActive || isTrial) && (
        <>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Choose a plan</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {PLANS.map((plan) => (
              <div
                key={plan.slug}
                className={`bg-white border rounded-2xl p-6 relative ${
                  plan.popular ? 'border-orange-300 ring-1 ring-orange-100' : 'border-gray-200/60'
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-orange-500 text-white text-[10px] font-bold uppercase tracking-wide">
                    Most Popular
                  </div>
                )}
                <h3 className="text-base font-semibold text-gray-900 mb-1">{plan.name}</h3>
                <div className="flex items-baseline gap-1 mb-5">
                  <span className="text-3xl font-bold text-gray-900">{plan.price}</span>
                  <span className="text-sm text-gray-400">/mo</span>
                </div>
                <button
                  onClick={() => handleCheckout(plan.priceId)}
                  disabled={!!actionLoading}
                  className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-colors cursor-pointer disabled:opacity-50 ${
                    plan.popular
                      ? 'bg-orange-500 hover:bg-orange-600 text-white'
                      : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                  }`}
                >
                  {actionLoading === plan.priceId ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                      Loading...
                    </span>
                  ) : (
                    'Subscribe'
                  )}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
