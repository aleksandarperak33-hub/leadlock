import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { DollarSign, TrendingUp, Users } from 'lucide-react';

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
        <div className="h-6 w-40 rounded bg-gray-100 animate-pulse" />
        <div className="grid grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-gray-100 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const totalMrr = revenue?.total_mrr || 0;
  const mrrByTier = revenue?.mrr_by_tier || {};
  const topClients = revenue?.top_clients || [];
  const totalClients = revenue?.total_paying_clients || 0;

  const summaryCards = [
    {
      label: 'Total MRR',
      value: `$${totalMrr.toLocaleString()}`,
      sub: `${totalClients} paying clients`,
      icon: DollarSign,
      iconBg: 'bg-emerald-50',
      iconColor: 'text-emerald-600',
    },
    {
      label: 'Annualized',
      value: `$${(totalMrr * 12).toLocaleString()}`,
      sub: 'projected ARR',
      icon: TrendingUp,
      iconBg: 'bg-orange-50',
      iconColor: 'text-orange-600',
    },
    {
      label: 'Avg per Client',
      value: `$${totalClients > 0 ? Math.round(totalMrr / totalClients).toLocaleString() : '0'}`,
      sub: 'monthly revenue',
      icon: Users,
      iconBg: 'bg-amber-50',
      iconColor: 'text-amber-600',
    },
  ];

  return (
    <div style={{ background: '#f8f9fb' }}>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold tracking-tight text-gray-900">Revenue</h1>
        <div className="flex gap-1.5">
          {['7d', '30d', '90d'].map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all cursor-pointer border ${
                period === p
                  ? 'bg-orange-50 text-orange-700 border-orange-200'
                  : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50 hover:text-gray-700'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        {summaryCards.map(({ label, value, sub, icon: Icon, iconBg, iconColor }) => (
          <div key={label} className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-medium uppercase tracking-wider text-gray-500">{label}</p>
              <div className={`w-8 h-8 rounded-lg ${iconBg} flex items-center justify-center`}>
                <Icon className={`w-4 h-4 ${iconColor}`} />
              </div>
            </div>
            <p className="text-2xl font-semibold font-mono text-gray-900">{value}</p>
            <p className="text-xs mt-1.5 text-gray-400">{sub}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* MRR by Tier */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">MRR by Tier</h3>
          <div className="space-y-3">
            {Object.entries(mrrByTier).sort((a, b) => b[1] - a[1]).map(([tier, mrr]) => {
              const pct = totalMrr > 0 ? ((mrr / totalMrr) * 100).toFixed(0) : 0;
              return (
                <div key={tier}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm capitalize text-gray-700">{tier}</span>
                    <span className="text-sm font-mono font-medium text-gray-900">
                      ${mrr.toLocaleString()} <span className="text-gray-400">({pct}%)</span>
                    </span>
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
            {Object.keys(mrrByTier).length === 0 && (
              <p className="text-sm text-gray-400">No tier data</p>
            )}
          </div>
        </div>

        {/* Top Clients by Revenue */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Top Clients by Revenue</h3>
          <div className="space-y-0.5">
            {topClients.map((client, i) => (
              <div key={client.id || i} className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-0">
                <div className="flex items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs font-mono font-medium text-gray-500">{i + 1}</span>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{client.business_name}</p>
                    <p className="text-xs capitalize text-gray-400">{client.trade_type} &middot; {client.tier}</p>
                  </div>
                </div>
                <span className="text-sm font-mono font-semibold text-emerald-600">
                  ${client.mrr?.toLocaleString() || '0'}
                </span>
              </div>
            ))}
            {topClients.length === 0 && (
              <p className="text-sm text-gray-400">No revenue data</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
