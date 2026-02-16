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
        <div className="h-6 w-48 rounded animate-pulse" style={{ background: 'var(--surface-2)' }} />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 rounded-card animate-pulse" style={{ background: 'var(--surface-1)' }} />
          ))}
        </div>
        <div className="h-64 rounded-card animate-pulse" style={{ background: 'var(--surface-1)' }} />
      </div>
    );
  }

  const metrics = overview ? [
    {
      label: 'Active Clients',
      value: overview.active_clients,
      accent: '#7c5bf0',
    },
    {
      label: 'Monthly Revenue',
      value: `$${(overview.total_mrr || 0).toLocaleString()}`,
      sub: `${overview.clients_by_billing?.active || 0} paying`,
      accent: '#34d399',
    },
    {
      label: 'Leads (30d)',
      value: overview.total_leads_30d,
      sub: `${overview.total_leads_7d} this week`,
      accent: '#5a72f0',
    },
    {
      label: 'Avg Response',
      value: overview.avg_response_time_ms ? `${(overview.avg_response_time_ms / 1000).toFixed(1)}s` : '—',
      sub: `${((overview.conversion_rate || 0) * 100).toFixed(1)}% conversion`,
      accent: '#fbbf24',
    },
  ] : [];

  const tierData = overview?.clients_by_tier || {};
  const billingData = overview?.clients_by_billing || {};

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>System Overview</h1>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full animate-live-pulse" style={{ background: '#34d399' }} />
          <span className="text-[11px] font-medium" style={{ color: 'var(--text-tertiary)' }}>Live</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {metrics.map(({ label, value, sub, accent }) => (
          <div
            key={label}
            className="relative overflow-hidden rounded-card p-4"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
          >
            <div className="absolute left-0 top-3 bottom-3 w-[2px] rounded-full" style={{ background: accent, opacity: 0.6 }} />
            <div className="pl-2.5">
              <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
              <p className="text-xl font-semibold font-mono mt-1" style={{ color: 'var(--text-primary)' }}>{value}</p>
              {sub && <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Clients by Tier */}
        <div className="rounded-card p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <h3 className="text-[11px] font-medium uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>Clients by Tier</h3>
          <div className="space-y-2.5">
            {Object.entries(tierData).sort((a, b) => b[1] - a[1]).map(([tier, count]) => {
              const total = Object.values(tierData).reduce((s, v) => s + v, 0) || 1;
              const pct = ((count / total) * 100).toFixed(0);
              return (
                <div key={tier}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{tier}</span>
                    <span className="text-[11px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{count} ({pct}%)</span>
                  </div>
                  <div className="w-full h-1.5 rounded-full" style={{ background: 'var(--surface-3)' }}>
                    <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, background: 'var(--accent)', opacity: 0.7 }} />
                  </div>
                </div>
              );
            })}
            {Object.keys(tierData).length === 0 && (
              <p className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>No tier data</p>
            )}
          </div>
        </div>

        {/* Billing Status */}
        <div className="rounded-card p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <h3 className="text-[11px] font-medium uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>Billing Status</h3>
          <div className="space-y-2.5">
            {Object.entries(billingData).sort((a, b) => b[1] - a[1]).map(([status, count]) => {
              const color = status === 'active' ? '#34d399' : status === 'trial' ? '#fbbf24' : status === 'past_due' ? '#f87171' : 'var(--text-tertiary)';
              return (
                <div key={status} className="flex items-center justify-between py-1.5" style={{ borderBottom: '1px solid var(--border)' }}>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
                    <span className="text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{status.replace('_', ' ')}</span>
                  </div>
                  <span className="text-[12px] font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{count}</span>
                </div>
              );
            })}
            {Object.keys(billingData).length === 0 && (
              <p className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>No billing data</p>
            )}
          </div>
        </div>

        {/* System Health */}
        <div className="rounded-card p-5 lg:col-span-2" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <h3 className="text-[11px] font-medium uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>System Health (24h)</h3>
          {health ? (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Errors (24h)</p>
                <p className="text-lg font-mono font-semibold mt-0.5" style={{ color: (health.error_count_24h || 0) > 0 ? '#f87171' : '#34d399' }}>
                  {health.error_count_24h || 0}
                </p>
              </div>
              <div>
                <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Pending Integrations</p>
                <p className="text-lg font-mono font-semibold mt-0.5" style={{ color: 'var(--text-primary)' }}>
                  {health.pending_integrations?.length || 0}
                </p>
              </div>
              <div>
                <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Recent Errors</p>
                <p className="text-lg font-mono font-semibold mt-0.5" style={{ color: (health.recent_errors?.length || 0) > 0 ? '#f87171' : '#34d399' }}>
                  {health.recent_errors?.length || 0}
                </p>
              </div>
              <div>
                <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Total Booked (30d)</p>
                <p className="text-lg font-mono font-semibold mt-0.5" style={{ color: 'var(--text-primary)' }}>
                  {overview?.total_booked_30d || 0}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>Health data unavailable</p>
          )}
        </div>
      </div>
    </div>
  );
}
