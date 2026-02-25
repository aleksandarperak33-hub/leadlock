import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import { Building2, DollarSign, Users, Clock } from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import StatCard from '../../components/ui/StatCard';
import Badge from '../../components/ui/Badge';
import StatusDot from '../../components/ui/StatusDot';

/**
 * Resolves a billing status string to a Badge variant.
 */
const billingVariant = (status) => {
  switch (status) {
    case 'active': return 'success';
    case 'trial': return 'warning';
    case 'past_due': return 'danger';
    case 'cancelled': return 'danger';
    default: return 'neutral';
  }
};

/**
 * Resolves an error-count value to a StatusDot color.
 */
const healthDotColor = (count) => {
  if (count === 0) return 'green';
  if (count <= 5) return 'yellow';
  return 'red';
};

/**
 * Progress bar colors by tier rank (index 0 = top tier).
 */
const TIER_BAR_COLORS = [
  'bg-orange-500',
  'bg-orange-400',
  'bg-orange-300',
  'bg-gray-400',
];

export default function AdminOverview() {
  const [overview, setOverview] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [ov, hl] = await Promise.all([
        api.getAdminOverview(),
        api.getAdminHealth(),
      ]);
      setOverview(ov);
      setHealth(hl);
    } catch (e) {
      console.error('Failed to fetch admin overview:', e);
      setError(e.message || 'Failed to load overview data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="bg-[#FAFAFA] min-h-screen space-y-6">
        <div className="h-7 w-48 rounded-lg bg-gray-100 animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 rounded-2xl bg-gray-100 animate-pulse" />
          ))}
        </div>
        <div className="h-64 rounded-2xl bg-gray-100 animate-pulse" />
      </div>
    );
  }

  const tierData = overview?.clients_by_tier || {};
  const billingData = overview?.clients_by_billing || {};
  const sortedTiers = Object.entries(tierData).sort((a, b) => b[1] - a[1]);
  const tierTotal = Object.values(tierData).reduce((s, v) => s + v, 0) || 1;

  const errorCount = health?.error_count_24h || 0;
  const pendingIntegrations = health?.pending_integrations?.length || 0;
  const recentErrors = health?.recent_errors?.length || 0;

  const healthItems = [
    { label: 'Errors (24h)', value: errorCount, color: healthDotColor(errorCount) },
    { label: 'Pending Integrations', value: pendingIntegrations, color: pendingIntegrations > 0 ? 'yellow' : 'green' },
    { label: 'Recent Errors', value: recentErrors, color: healthDotColor(recentErrors) },
    { label: 'Booked (30d)', value: overview?.total_booked_30d || 0, color: 'green' },
  ];

  return (
    <div className="bg-[#FAFAFA] min-h-screen">
      <PageHeader title="System Overview" />

      {error && (
        <div className="mb-6 flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-sm text-red-700">
          <span>{error}</span>
          <button
            onClick={() => { setLoading(true); fetchData(); }}
            className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium text-red-700 bg-white border border-red-200 hover:bg-red-100 transition-colors cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          label="Active Clients"
          value={overview?.active_clients ?? 0}
          icon={Building2}
          color="brand"
        />
        <StatCard
          label="Monthly Revenue"
          value={`$${(overview?.total_mrr || 0).toLocaleString()}`}
          deltaLabel={`${overview?.clients_by_billing?.active || 0} paying`}
          icon={DollarSign}
          color="green"
        />
        <StatCard
          label="Leads (30d)"
          value={overview?.total_leads_30d ?? 0}
          deltaLabel={`${overview?.total_leads_7d || 0} this week`}
          icon={Users}
          color="brand"
        />
        <StatCard
          label="Avg Response Time"
          value={
            overview?.avg_response_time_ms
              ? `${(overview.avg_response_time_ms / 1000).toFixed(1)}s`
              : '\u2014'
          }
          deltaLabel={`${((overview?.conversion_rate || 0) * 100).toFixed(1)}% conversion`}
          icon={Clock}
          color="yellow"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Clients by Tier */}
        <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card">
          <h3 className="text-lg font-semibold text-gray-900 mb-5">Clients by Tier</h3>
          <div className="space-y-4">
            {sortedTiers.map(([tier, count], idx) => {
              const pct = ((count / tierTotal) * 100).toFixed(0);
              const barColor = TIER_BAR_COLORS[idx] || TIER_BAR_COLORS[TIER_BAR_COLORS.length - 1];
              return (
                <div key={tier}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm font-medium capitalize text-gray-700">{tier}</span>
                    <span className="text-xs font-mono text-gray-400">
                      {count} ({pct}%)
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-gray-100">
                    <div
                      className={`h-2 rounded-full transition-all ${barColor}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
            {sortedTiers.length === 0 && (
              <p className="text-sm text-gray-400">No tier data</p>
            )}
          </div>
        </div>

        {/* Billing Status */}
        <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card">
          <h3 className="text-lg font-semibold text-gray-900 mb-5">Billing Status</h3>
          <div className="space-y-0.5">
            {Object.entries(billingData).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
              <div
                key={status}
                className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0"
              >
                <div className="flex items-center gap-3">
                  <Badge variant={billingVariant(status)} size="sm">
                    {status.replace('_', ' ')}
                  </Badge>
                </div>
                <span className="text-sm font-mono font-medium text-gray-900">{count}</span>
              </div>
            ))}
            {Object.keys(billingData).length === 0 && (
              <p className="text-sm text-gray-400">No billing data</p>
            )}
          </div>
        </div>

        {/* System Health */}
        <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card lg:col-span-2">
          <h3 className="text-lg font-semibold text-gray-900 mb-5">System Health</h3>
          {health ? (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {healthItems.map(({ label, value, color }) => (
                <div
                  key={label}
                  className="bg-white border border-gray-200/50 rounded-xl p-4 shadow-card"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <StatusDot color={color} />
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                      {label}
                    </span>
                  </div>
                  <p className={`text-2xl font-bold font-mono ${
                    color === 'red' ? 'text-red-600' :
                    color === 'yellow' ? 'text-amber-600' :
                    'text-gray-900'
                  }`}>
                    {value}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">Health data unavailable</p>
          )}
        </div>
      </div>
    </div>
  );
}
