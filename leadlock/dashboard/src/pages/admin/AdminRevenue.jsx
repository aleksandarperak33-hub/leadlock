import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { DollarSign, TrendingUp, BarChart3 } from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import Tabs from '../../components/ui/Tabs';
import StatCard from '../../components/ui/StatCard';

const PERIOD_TABS = [
  { id: '30d', label: '30d' },
  { id: '90d', label: '90d' },
  { id: '12m', label: '12m' },
];

/**
 * Progress bar colors by tier rank (index 0 = highest revenue tier).
 */
const TIER_BAR_COLORS = [
  'bg-orange-500',
  'bg-orange-400',
  'bg-orange-300',
  'bg-gray-400',
];

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
      <div className="bg-[#FAFAFA] min-h-screen space-y-6">
        <div className="h-7 w-40 rounded-lg bg-gray-100 animate-pulse" />
        <div className="grid grid-cols-3 gap-6">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 rounded-2xl bg-gray-100 animate-pulse" />
          ))}
        </div>
        <div className="grid grid-cols-2 gap-6">
          <div className="h-64 rounded-2xl bg-gray-100 animate-pulse" />
          <div className="h-64 rounded-2xl bg-gray-100 animate-pulse" />
        </div>
      </div>
    );
  }

  const totalMrr = revenue?.total_mrr || 0;
  const mrrByTier = revenue?.mrr_by_tier || {};
  const topClients = revenue?.top_clients || [];
  const totalClients = revenue?.total_paying_clients || 0;
  const sortedTiers = Object.entries(mrrByTier).sort((a, b) => b[1] - a[1]);

  return (
    <div className="bg-[#FAFAFA] min-h-screen">
      <PageHeader
        title="Revenue"
        actions={
          <Tabs
            tabs={PERIOD_TABS}
            activeId={period}
            onChange={setPeriod}
          />
        }
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <StatCard
          label="Total MRR"
          value={`$${totalMrr.toLocaleString()}`}
          deltaLabel={`${totalClients} paying clients`}
          icon={DollarSign}
          color="green"
        />
        <StatCard
          label="Annualized Revenue"
          value={`$${(totalMrr * 12).toLocaleString()}`}
          deltaLabel="projected ARR"
          icon={TrendingUp}
          color="brand"
        />
        <StatCard
          label="Avg Revenue per Client"
          value={`$${totalClients > 0 ? Math.round(totalMrr / totalClients).toLocaleString() : '0'}`}
          deltaLabel="monthly revenue"
          icon={BarChart3}
          color="brand"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* MRR by Tier */}
        <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card">
          <h3 className="text-lg font-semibold text-gray-900 mb-5">MRR by Tier</h3>
          <div className="space-y-4">
            {sortedTiers.map(([tier, mrr], idx) => {
              const pct = totalMrr > 0 ? ((mrr / totalMrr) * 100).toFixed(0) : 0;
              const barColor = TIER_BAR_COLORS[idx] || TIER_BAR_COLORS[TIER_BAR_COLORS.length - 1];
              return (
                <div key={tier}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm font-medium capitalize text-gray-700">{tier}</span>
                    <span className="text-sm font-mono font-medium text-gray-900">
                      ${mrr.toLocaleString()}
                      <span className="text-gray-400 ml-1">({pct}%)</span>
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

        {/* Top Clients by Revenue */}
        <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card">
          <h3 className="text-lg font-semibold text-gray-900 mb-5">Top Clients by Revenue</h3>
          <div className="space-y-0.5">
            {topClients.map((client, i) => (
              <div
                key={client.id || i}
                className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0"
              >
                <div className="flex items-center gap-3">
                  <span className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center text-xs font-mono font-semibold text-gray-500">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{client.business_name}</p>
                    <p className="text-xs capitalize text-gray-400">
                      {client.trade_type} &middot; {client.tier}
                    </p>
                  </div>
                </div>
                <span className="text-sm font-mono font-semibold text-gray-900">
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
