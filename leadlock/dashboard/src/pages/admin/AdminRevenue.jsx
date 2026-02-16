import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { DollarSign, TrendingUp } from 'lucide-react';

export default function AdminRevenue() {
  const [revenue, setRevenue] = useState(null);
  const [period, setPeriod] = useState('30d');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchRevenue = async () => {
      setLoading(true);
      try {
        const data = await api.getAdminRevenue(period);
        setRevenue(data);
      } catch (e) {
        console.error('Failed to fetch revenue:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchRevenue();
  }, [period]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-40 rounded animate-pulse" style={{ background: 'var(--surface-2)' }} />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 rounded-card animate-pulse" style={{ background: 'var(--surface-1)' }} />
          ))}
        </div>
      </div>
    );
  }

  const totalMrr = revenue?.total_mrr || 0;
  const mrrByTier = revenue?.mrr_by_tier || {};
  const topClients = revenue?.top_clients || [];
  const totalClients = revenue?.total_paying_clients || 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Revenue</h1>
        <div className="flex gap-1">
          {['7d', '30d', '90d'].map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className="px-2.5 py-1 text-[11px] font-medium rounded-md transition-all"
              style={{
                background: period === p ? 'var(--accent-muted)' : 'transparent',
                color: period === p ? 'var(--accent)' : 'var(--text-tertiary)',
                border: period === p ? '1px solid rgba(124, 91, 240, 0.2)' : '1px solid var(--border)',
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-6">
        <div className="relative overflow-hidden rounded-card p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <div className="absolute left-0 top-4 bottom-4 w-[2px] rounded-full" style={{ background: '#34d399', opacity: 0.6 }} />
          <div className="pl-3">
            <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Total MRR</p>
            <p className="text-2xl font-semibold font-mono mt-1" style={{ color: 'var(--text-primary)' }}>
              ${totalMrr.toLocaleString()}
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{totalClients} paying clients</p>
          </div>
        </div>
        <div className="relative overflow-hidden rounded-card p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <div className="absolute left-0 top-4 bottom-4 w-[2px] rounded-full" style={{ background: '#7c5bf0', opacity: 0.6 }} />
          <div className="pl-3">
            <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Annualized</p>
            <p className="text-2xl font-semibold font-mono mt-1" style={{ color: 'var(--text-primary)' }}>
              ${(totalMrr * 12).toLocaleString()}
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>projected ARR</p>
          </div>
        </div>
        <div className="relative overflow-hidden rounded-card p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <div className="absolute left-0 top-4 bottom-4 w-[2px] rounded-full" style={{ background: '#fbbf24', opacity: 0.6 }} />
          <div className="pl-3">
            <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Avg per Client</p>
            <p className="text-2xl font-semibold font-mono mt-1" style={{ color: 'var(--text-primary)' }}>
              ${totalClients > 0 ? Math.round(totalMrr / totalClients).toLocaleString() : '0'}
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>monthly revenue</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* MRR by Tier */}
        <div className="rounded-card p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <h3 className="text-[11px] font-medium uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>MRR by Tier</h3>
          <div className="space-y-3">
            {Object.entries(mrrByTier).sort((a, b) => b[1] - a[1]).map(([tier, mrr]) => {
              const pct = totalMrr > 0 ? ((mrr / totalMrr) * 100).toFixed(0) : 0;
              return (
                <div key={tier}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{tier}</span>
                    <span className="text-[12px] font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                      ${mrr.toLocaleString()} <span style={{ color: 'var(--text-tertiary)' }}>({pct}%)</span>
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full" style={{ background: 'var(--surface-3)' }}>
                    <div className="h-1.5 rounded-full transition-all" style={{ width: `${pct}%`, background: 'var(--accent)', opacity: 0.7 }} />
                  </div>
                </div>
              );
            })}
            {Object.keys(mrrByTier).length === 0 && (
              <p className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>No tier data</p>
            )}
          </div>
        </div>

        {/* Top Clients by Revenue */}
        <div className="rounded-card p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <h3 className="text-[11px] font-medium uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>Top Clients by Revenue</h3>
          <div className="space-y-1">
            {topClients.map((client, i) => (
              <div key={client.id || i} className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid var(--border)' }}>
                <div className="flex items-center gap-2.5">
                  <span className="w-5 text-[11px] font-mono text-center" style={{ color: 'var(--text-tertiary)' }}>{i + 1}</span>
                  <div>
                    <p className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>{client.business_name}</p>
                    <p className="text-[11px] capitalize" style={{ color: 'var(--text-tertiary)' }}>{client.trade_type} &middot; {client.tier}</p>
                  </div>
                </div>
                <span className="text-[13px] font-mono font-medium" style={{ color: '#34d399' }}>
                  ${client.mrr?.toLocaleString() || '0'}
                </span>
              </div>
            ))}
            {topClients.length === 0 && (
              <p className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>No revenue data</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
