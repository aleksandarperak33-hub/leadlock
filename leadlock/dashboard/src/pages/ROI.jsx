import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { CHART_COLORS, TOOLTIP_STYLE, SOURCE_BAR_PALETTE } from '../lib/colors';
import PageHeader from '../components/ui/PageHeader';
import StatCard from '../components/ui/StatCard';
import FunnelChart from '../components/FunnelChart';
import {
  Users,
  CalendarCheck,
  DollarSign,
  Zap,
  Timer,
  TrendingUp,
  BarChart3,
  Target,
  Clock,
  FlaskConical,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ScatterChart,
  Scatter,
  Cell,
  Legend,
} from 'recharts';

const PERIODS = [
  { id: '7d', label: '7 Days' },
  { id: '30d', label: '30 Days' },
  { id: '90d', label: '90 Days' },
  { id: 'all', label: 'All Time' },
];

const SOURCE_COLORS = {
  google_lsa: '#4285f4',
  angi: '#00b050',
  facebook: '#1877f2',
  website: '#f97316',
  missed_call: '#8b5cf6',
  text_in: '#06b6d4',
  thumbtack: '#0fba81',
  yelp: '#d32323',
  referral: '#ec4899',
};

function formatCurrency(value) {
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`;
  return `$${value.toFixed(0)}`;
}

function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * SectionCard - Consistent card wrapper for each ROI section.
 */
function SectionCard({ title, icon: Icon, children, className = '' }) {
  return (
    <div className={`bg-white border border-gray-200/50 rounded-2xl shadow-card overflow-hidden ${className}`}>
      {title && (
        <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2.5">
          {Icon && <Icon className="w-4.5 h-4.5 text-orange-500" strokeWidth={1.75} />}
          <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  );
}

/**
 * ROI Dashboard - The showpiece. Makes the value undeniable.
 */
export default function ROI() {
  const [period, setPeriod] = useState('30d');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    api.getROI(period)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e.message || 'Failed to load ROI data'))
      .finally(() => setLoading(false));
  }, [period]);

  if (loading && !data) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <PageHeader title="ROI Dashboard" subtitle="Loading your performance data..." />
        <div className="flex items-center justify-center h-64">
          <div className="w-8 h-8 border-3 border-orange-200 border-t-orange-500 rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <PageHeader title="ROI Dashboard" />
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  const h = data?.hero_kpis || {};
  const funnel = data?.funnel || {};
  const revBySrc = data?.revenue_by_source || [];
  const revByMonth = data?.revenue_by_month || [];
  const economics = data?.per_lead_economics || {};
  const rtDist = data?.response_time_distribution || [];
  const variants = data?.qualify_variant_performance || [];

  const roiGlow = h.roi_multiplier > 10;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {/* Header + Period Selector */}
      <PageHeader
        title="ROI Dashboard"
        subtitle="Your investment is working. Here's the proof."
        actions={
          <div className="flex gap-1.5 bg-gray-100 rounded-xl p-1">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                onClick={() => setPeriod(p.id)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  period === p.id
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        }
      />

      {/* 1. Hero KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          label="Total Leads"
          value={h.total_leads?.toLocaleString() || '0'}
          icon={Users}
          color="brand"
        />
        <StatCard
          label="Booking Rate"
          value={formatPercent(h.booking_rate || 0)}
          icon={Target}
          color="green"
        />
        <StatCard
          label="Est. Revenue"
          value={formatCurrency(h.estimated_revenue || 0)}
          icon={DollarSign}
          color="green"
        />
        <StatCard
          label="Cost / Booked Lead"
          value={`$${(h.cost_per_booked_lead || 0).toFixed(2)}`}
          icon={BarChart3}
          color="blue"
        />
        <div className={roiGlow ? 'animate-pulse' : ''}>
          <StatCard
            label="ROI Multiplier"
            value={`${(h.roi_multiplier || 0).toFixed(1)}x`}
            icon={TrendingUp}
            color={roiGlow ? 'green' : 'brand'}
            deltaLabel={roiGlow ? 'Crushing it' : undefined}
          />
        </div>
        <StatCard
          label="Avg Response"
          value={`${(h.avg_response_time_seconds || 0).toFixed(1)}s`}
          icon={Timer}
          color={h.avg_response_time_seconds < 10 ? 'green' : 'yellow'}
          deltaLabel={`${formatPercent(h.leads_under_10s || 0)} under 10s`}
        />
      </div>

      {/* 2. Revenue Attribution + 3. Funnel side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue by Source */}
        <SectionCard title="Revenue by Source" icon={BarChart3}>
          {revBySrc.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={revBySrc} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
                <XAxis
                  dataKey="source"
                  tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
                  tickFormatter={(s) => s.replace(/_/g, ' ')}
                />
                <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} tickFormatter={formatCurrency} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(v, name) => [name === 'revenue' ? formatCurrency(v) : v, name]}
                />
                <Bar dataKey="revenue" radius={[6, 6, 0, 0]}>
                  {revBySrc.map((entry, i) => (
                    <Cell key={i} fill={SOURCE_COLORS[entry.source] || SOURCE_BAR_PALETTE[i % SOURCE_BAR_PALETTE.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 text-center py-12">No source data yet</p>
          )}
        </SectionCard>

        {/* Funnel */}
        <SectionCard title="Lead Funnel" icon={Target}>
          <FunnelChart data={funnel} />
          {/* Drop-off metrics */}
          <div className="mt-4 grid grid-cols-3 gap-3">
            {[
              { label: 'Intake Rate', val: funnel.intake_sent, base: funnel.new },
              { label: 'Qualify Rate', val: funnel.qualified, base: funnel.qualifying || funnel.intake_sent },
              { label: 'Book Rate', val: funnel.booked, base: funnel.qualified || funnel.booking },
            ].map(({ label, val, base }) => (
              <div key={label} className="text-center">
                <p className="text-xs text-gray-400 uppercase tracking-wider">{label}</p>
                <p className="text-lg font-bold text-gray-900">
                  {base > 0 ? formatPercent((val || 0) / base) : '--'}
                </p>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      {/* Revenue by Month */}
      {revByMonth.length > 1 && (
        <SectionCard title="Revenue Trend" icon={TrendingUp}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={revByMonth} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
              <XAxis dataKey="month" tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} />
              <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} tickFormatter={formatCurrency} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v, name) => [name === 'revenue' ? formatCurrency(v) : v, name]} />
              <Legend />
              <Bar dataKey="revenue" fill="#f97316" radius={[6, 6, 0, 0]} name="Revenue" />
              <Bar dataKey="leads" fill="#fdba74" radius={[6, 6, 0, 0]} name="Leads" />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      {/* 4. Per-Lead Economics + 5. Source Performance Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Per-Lead Economics */}
        <SectionCard title="Per-Lead Economics" icon={DollarSign}>
          <div className="space-y-4">
            {[
              { label: 'SMS Cost / Lead', value: `$${economics.avg_sms_cost?.toFixed(3) || '0.000'}` },
              { label: 'AI Cost / Lead', value: `$${economics.avg_ai_cost?.toFixed(3) || '0.000'}` },
              { label: 'Total Cost / Lead', value: `$${economics.avg_total_cost?.toFixed(3) || '0.000'}`, bold: true },
              { label: 'Avg Job Value', value: formatCurrency(economics.avg_job_value || 0) },
            ].map(({ label, value, bold }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="text-sm text-gray-500">{label}</span>
                <span className={`text-sm ${bold ? 'font-bold text-gray-900' : 'font-medium text-gray-700'}`}>{value}</span>
              </div>
            ))}
            {/* Visual: cost as tiny sliver vs revenue */}
            <div className="mt-4 pt-4 border-t border-gray-100">
              <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Cost vs Revenue per Lead</p>
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden relative">
                  <div
                    className="bg-emerald-500 h-full rounded-full"
                    style={{ width: '100%' }}
                  />
                  <div
                    className="absolute top-0 left-0 bg-red-400 h-full rounded-full"
                    style={{ width: `${Math.min((economics.cost_to_revenue_ratio || 0) * 100, 5)}%`, minWidth: '2px' }}
                  />
                </div>
                <span className="text-xs font-mono text-gray-500 whitespace-nowrap">
                  {((economics.cost_to_revenue_ratio || 0) * 100).toFixed(3)}%
                </span>
              </div>
              <div className="flex gap-4 mt-1.5 text-[10px] text-gray-400">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400" /> Cost</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Revenue</span>
              </div>
            </div>
          </div>
        </SectionCard>

        {/* Source Performance Cards */}
        <SectionCard title="Source Performance" icon={Zap}>
          <div className="grid grid-cols-2 gap-3">
            {revBySrc.map((src) => {
              const rate = src.leads > 0 ? src.booked / src.leads : 0;
              const borderColor = rate > 0.6 ? 'border-l-emerald-500' : rate > 0.3 ? 'border-l-orange-400' : 'border-l-red-400';
              return (
                <div key={src.source} className={`bg-gray-50 rounded-xl p-3.5 border-l-4 ${borderColor}`}>
                  <p className="text-xs font-medium text-gray-500 capitalize">{src.source.replace(/_/g, ' ')}</p>
                  <p className="text-lg font-bold text-gray-900 mt-1">{src.leads}</p>
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-[10px] text-gray-400">Book: {formatPercent(rate)}</span>
                    <span className="text-[10px] font-medium text-emerald-600">{formatCurrency(src.revenue)}</span>
                  </div>
                </div>
              );
            })}
            {revBySrc.length === 0 && (
              <p className="text-sm text-gray-400 text-center col-span-2 py-8">No source data yet</p>
            )}
          </div>
        </SectionCard>
      </div>

      {/* 6. Response Time Distribution */}
      <SectionCard title="Response Time Impact" icon={Clock}>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={rtDist} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
            <XAxis dataKey="bucket" tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} />
            <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Bar dataKey="count" radius={[6, 6, 0, 0]}>
              {rtDist.map((entry, i) => {
                const colors = { '0-5s': '#10b981', '5-10s': '#fb923c', '10-30s': '#f59e0b', '30s+': '#ef4444' };
                return <Cell key={i} fill={colors[entry.bucket] || '#f97316'} />;
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        {h.leads_under_10s > 0 && (
          <div className="mt-3 text-center">
            <p className="text-sm text-gray-500">
              <span className="font-bold text-emerald-600">{formatPercent(h.leads_under_10s)}</span> of leads responded to in under 10 seconds
            </p>
          </div>
        )}
      </SectionCard>

      {/* 7. Qualify Variant Performance (A/B Test) */}
      {variants.length > 0 && (
        <SectionCard title="Qualify Prompt A/B Test" icon={FlaskConical}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-2 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Variant</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Leads</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Booked</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Booking Rate</th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Performance</th>
                </tr>
              </thead>
              <tbody>
                {variants.map((v) => {
                  const best = Math.max(...variants.map((x) => x.rate));
                  const isBest = v.rate === best && v.rate > 0;
                  return (
                    <tr key={v.variant} className="border-b border-gray-50 hover:bg-gray-50/50">
                      <td className="py-3 px-3 font-medium text-gray-900">
                        Variant {v.variant}
                        {isBest && <span className="ml-2 text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full font-semibold">BEST</span>}
                      </td>
                      <td className="py-3 px-3 text-right text-gray-600">{v.leads}</td>
                      <td className="py-3 px-3 text-right text-gray-600">{v.booked}</td>
                      <td className="py-3 px-3 text-right font-bold text-gray-900">{formatPercent(v.rate)}</td>
                      <td className="py-3 px-3">
                        <div className="w-full bg-gray-100 rounded-full h-2.5">
                          <div
                            className={`h-2.5 rounded-full ${isBest ? 'bg-emerald-500' : 'bg-orange-400'}`}
                            style={{ width: `${Math.max(v.rate * 100, 2)}%` }}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {variants.length > 1 && (
            <p className="text-xs text-gray-400 mt-3 text-center">
              Deterministic assignment via lead ID hash. Statistical significance requires 100+ leads per variant.
            </p>
          )}
        </SectionCard>
      )}
    </div>
  );
}
