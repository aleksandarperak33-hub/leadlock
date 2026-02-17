import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { Users, DollarSign, FileText, Clock, TrendingUp, AlertTriangle } from 'lucide-react';

export default function AdminOverview() {
  const [overview, setOverview] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [ov, hl] = await Promise.all([
          api.getAdminOverview(),
          api.getAdminHealth(),
        ]);
        setOverview(ov);
        setHealth(hl);
      } catch (e) {
        console.error('Failed to fetch admin overview:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-48 rounded bg-gray-100 animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-gray-100 animate-pulse" />
          ))}
        </div>
        <div className="h-64 rounded-xl bg-gray-100 animate-pulse" />
      </div>
    );
  }

  const metrics = overview ? [
    {
      label: 'Active Clients',
      value: overview.active_clients,
      icon: Users,
      color: 'orange',
    },
    {
      label: 'Monthly Revenue',
      value: `$${(overview.total_mrr || 0).toLocaleString()}`,
      sub: `${overview.clients_by_billing?.active || 0} paying`,
      icon: DollarSign,
      color: 'emerald',
    },
    {
      label: 'Leads (30d)',
      value: overview.total_leads_30d,
      sub: `${overview.total_leads_7d} this week`,
      icon: FileText,
      color: 'blue',
    },
    {
      label: 'Avg Response',
      value: overview.avg_response_time_ms ? `${(overview.avg_response_time_ms / 1000).toFixed(1)}s` : '\u2014',
      sub: `${((overview.conversion_rate || 0) * 100).toFixed(1)}% conversion`,
      icon: Clock,
      color: 'amber',
    },
  ] : [];

  const iconBgMap = {
    orange: 'bg-orange-50',
    emerald: 'bg-emerald-50',
    blue: 'bg-blue-50',
    amber: 'bg-amber-50',
  };
  const iconColorMap = {
    orange: 'text-orange-600',
    emerald: 'text-emerald-600',
    blue: 'text-blue-600',
    amber: 'text-amber-600',
  };

  const tierData = overview?.clients_by_tier || {};
  const billingData = overview?.clients_by_billing || {};

  const billingDotColor = (status) => {
    switch (status) {
      case 'active': return 'bg-emerald-500';
      case 'trial': return 'bg-amber-500';
      case 'past_due': return 'bg-red-500';
      default: return 'bg-gray-400';
    }
  };

  const billingTextColor = (status) => {
    switch (status) {
      case 'active': return 'text-emerald-700';
      case 'trial': return 'text-amber-700';
      case 'past_due': return 'text-red-700';
      default: return 'text-gray-500';
    }
  };

  return (
    <div className="min-h-screen" style={{ background: '#f8f9fb' }}>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold tracking-tight text-gray-900">System Overview</h1>
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="text-xs font-medium text-gray-400">Live</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {metrics.map(({ label, value, sub, icon: Icon, color }) => (
          <div
            key={label}
            className="bg-white border border-gray-200 rounded-xl shadow-sm p-4"
          >
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-medium uppercase tracking-wider text-gray-500">{label}</p>
              <div className={`w-8 h-8 rounded-lg ${iconBgMap[color]} flex items-center justify-center`}>
                <Icon className={`w-4 h-4 ${iconColorMap[color]}`} />
              </div>
            </div>
            <p className="text-2xl font-semibold font-mono text-gray-900">{value}</p>
            {sub && <p className="text-xs mt-1 text-gray-400">{sub}</p>}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Clients by Tier */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Clients by Tier</h3>
          <div className="space-y-3">
            {Object.entries(tierData).sort((a, b) => b[1] - a[1]).map(([tier, count]) => {
              const total = Object.values(tierData).reduce((s, v) => s + v, 0) || 1;
              const pct = ((count / total) * 100).toFixed(0);
              return (
                <div key={tier}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm capitalize text-gray-700">{tier}</span>
                    <span className="text-xs font-mono text-gray-400">{count} ({pct}%)</span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-gray-100">
                    <div
                      className="h-1.5 rounded-full bg-orange-500 transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
            {Object.keys(tierData).length === 0 && (
              <p className="text-sm text-gray-400">No tier data</p>
            )}
          </div>
        </div>

        {/* Billing Status */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Billing Status</h3>
          <div className="space-y-0.5">
            {Object.entries(billingData).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
              <div key={status} className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-0">
                <div className="flex items-center gap-2.5">
                  <span className={`w-2 h-2 rounded-full ${billingDotColor(status)}`} />
                  <span className="text-sm capitalize text-gray-600">{status.replace('_', ' ')}</span>
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
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 lg:col-span-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">System Health (24h)</h3>
          {health ? (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="text-xs text-gray-500">Errors (24h)</p>
                <p className={`text-xl font-mono font-semibold mt-1 ${(health.error_count_24h || 0) > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                  {health.error_count_24h || 0}
                </p>
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="text-xs text-gray-500">Pending Integrations</p>
                <p className="text-xl font-mono font-semibold mt-1 text-gray-900">
                  {health.pending_integrations?.length || 0}
                </p>
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="text-xs text-gray-500">Recent Errors</p>
                <p className={`text-xl font-mono font-semibold mt-1 ${(health.recent_errors?.length || 0) > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                  {health.recent_errors?.length || 0}
                </p>
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="text-xs text-gray-500">Total Booked (30d)</p>
                <p className="text-xl font-mono font-semibold mt-1 text-gray-900">
                  {overview?.total_booked_30d || 0}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400">Health data unavailable</p>
          )}
        </div>
      </div>
    </div>
  );
}
