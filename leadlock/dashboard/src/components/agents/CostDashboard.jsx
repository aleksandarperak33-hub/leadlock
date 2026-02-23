import { useState, useEffect, useCallback } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { DollarSign, TrendingUp, Calendar } from 'lucide-react';
import { api } from '../../api/client';
import StatCard from '../ui/StatCard';

const PERIODS = ['7d', '30d', '90d'];

const AGENT_COLORS = {
  outreach_sequencer: '#ef4444',
  ab_test_engine: '#a855f7',
  winback_agent: '#f59e0b',
  reflection_agent: '#6366f1',
  referral_agent: '#ec4899',
  sms_dispatch: '#0ea5e9',
  lead_state_manager: '#84cc16',
  crm_sync: '#f97316',
  scraper: '#06b6d4',
  task_processor: '#6b7280',
  system_health: '#22c55e',
  outreach_monitor: '#10b981',
  retry_worker: '#78716c',
  registration_poller: '#8b5cf6',
};

const AGENT_LABELS = {
  outreach_sequencer: 'Sequencer',
  ab_test_engine: 'A/B Testing',
  winback_agent: 'Win-Back',
  reflection_agent: 'Reflection',
  referral_agent: 'Referral',
  sms_dispatch: 'SMS Dispatch',
  lead_state_manager: 'Lead State',
  crm_sync: 'CRM Sync',
  scraper: 'Scraper',
  task_processor: 'Tasks',
  system_health: 'Sys Health',
  outreach_monitor: 'Outreach Mon',
  retry_worker: 'Retry',
  registration_poller: 'A2P Reg',
};

/**
 * Cost tracking dashboard with stacked area chart and per-agent table.
 */
export default function CostDashboard() {
  const [period, setPeriod] = useState('7d');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchCosts = useCallback(() => {
    setLoading(true);
    setError(null);
    api.getAgentCosts(period)
      .then((res) => {
        setData(res.data);
      })
      .catch((err) => {
        setError(err.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [period]);

  useEffect(() => { fetchCosts(); }, [fetchCosts]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-orange-200 border-t-orange-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card p-6 text-center">
        <p className="text-red-600 text-sm mb-2">{error}</p>
        <button
          onClick={fetchCosts}
          className="text-sm text-orange-600 hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const agentNames = Object.keys(AGENT_COLORS);
  const chartData = (data.daily || []).map((d) => ({
    ...d,
    date: d.date?.slice(5),
  }));

  // Sort agents by total cost descending for the table
  const sortedAgents = agentNames
    .map((name) => ({
      name,
      label: AGENT_LABELS[name],
      color: AGENT_COLORS[name],
      total: data.agent_totals?.[name] ?? 0,
    }))
    .sort((a, b) => b.total - a.total);

  return (
    <div className="space-y-6 animate-fade-up">
      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="TOTAL COST"
          value={`$${data.grand_total?.toFixed(3) ?? '0.000'}`}
          icon={DollarSign}
          color="blue"
        />
        <StatCard
          label="DAILY AVERAGE"
          value={`$${data.daily_average?.toFixed(4) ?? '0.0000'}`}
          icon={TrendingUp}
          color="green"
        />
        <StatCard
          label="PROJECTED MONTHLY"
          value={`$${data.projected_monthly?.toFixed(2) ?? '0.00'}`}
          icon={Calendar}
          color="purple"
        />
      </div>

      {/* Period selector + chart */}
      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-900">Cost by Agent</h3>
          <div className="flex gap-1">
            {PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors ${
                  period === p
                    ? 'bg-orange-500 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${v}`}
              width={50}
            />
            <Tooltip
              formatter={(value, name) => [`$${Number(value).toFixed(4)}`, AGENT_LABELS[name] || name]}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
            />
            <Legend
              formatter={(value) => AGENT_LABELS[value] || value}
              wrapperStyle={{ fontSize: 11 }}
            />
            {agentNames.map((name) => (
              <Area
                key={name}
                type="monotone"
                dataKey={name}
                stackId="cost"
                stroke={AGENT_COLORS[name]}
                fill={AGENT_COLORS[name]}
                fillOpacity={0.3}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Per-agent cost table */}
      <div className="glass-card p-6">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Per-Agent Breakdown</h3>
        <div className="divide-y divide-gray-100">
          {sortedAgents.map(({ name, label, color, total }) => {
            const pct = data.grand_total > 0 ? (total / data.grand_total) * 100 : 0;
            const dailyAvg = data.days > 0 ? total / data.days : 0;
            return (
              <div key={name} className="flex items-center justify-between py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                  <span className="text-sm text-gray-700">{label}</span>
                </div>
                <div className="flex items-center gap-6 text-xs text-gray-500">
                  <span className="font-mono w-16 text-right">${total.toFixed(4)}</span>
                  <span className="w-12 text-right">{pct.toFixed(1)}%</span>
                  <span className="font-mono w-20 text-right">${dailyAvg.toFixed(4)}/d</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
