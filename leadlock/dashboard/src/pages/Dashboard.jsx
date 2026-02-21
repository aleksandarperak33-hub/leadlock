import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { POLL_INTERVALS } from '../lib/constants';
import { responseTimeColor } from '../lib/response-time';
import PageHeader from '../components/ui/PageHeader';
import StatCard from '../components/ui/StatCard';
import ResponseTimeChart from '../components/ResponseTimeChart';
import SourceBreakdown from '../components/SourceBreakdown';
import LiveIndicator from '../components/LiveIndicator';
import {
  Users,
  CalendarCheck,
  Timer,
  Gauge,
  Activity,
  TrendingUp,
  Clock,
  PieChart,
  AlertCircle,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { formatDistanceToNow } from 'date-fns';

const PERIODS = [
  { id: '7d', label: '7d' },
  { id: '30d', label: '30d' },
  { id: '90d', label: '90d' },
];

const ACTIVITY_DOT_COLORS = {
  booking_confirmed: 'bg-emerald-500',
  lead_created: 'bg-orange-500',
  opt_out: 'bg-red-500',
};

const TOOLTIP_STYLE = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: '12px',
  color: '#111827',
  fontSize: '12px',
  boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
  padding: '10px 14px',
};

/**
 * Dashboard -- Overview page with KPI cards, charts, and activity feed.
 * Fetches metrics and activity data with auto-refresh.
 */
export default function Dashboard() {
  const [period, setPeriod] = useState('7d');
  const [metrics, setMetrics] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    try {
      const [m, a] = await Promise.all([
        api.getMetrics(period),
        api.getActivity(20),
      ]);
      setMetrics(m);
      setActivity(a);
      setError(null);
    } catch (e) {
      console.error('Failed to fetch dashboard data:', e);
      setError(e.message || 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVALS.DASHBOARD);
    return () => clearInterval(interval);
  }, [period]);

  const hasResponseData = metrics && (metrics.avg_response_time_ms > 0 || metrics.total_leads > 0);
  const avgResponseSec = metrics
    ? hasResponseData
      ? (metrics.avg_response_time_ms / 1000).toFixed(1)
      : '\u2014'
    : '\u2014';
  const avgResponseColor = hasResponseData
    ? responseTimeColor(metrics.avg_response_time_ms)
    : 'brand';

  if (loading && !metrics) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-40 rounded-lg bg-gray-100 animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-32 rounded-2xl bg-white border border-gray-200/60 animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  const periodActions = (
    <div className="flex items-center gap-4">
      <LiveIndicator />
      <div className="flex rounded-xl p-1 bg-gray-100/80 border border-gray-200/60">
        {PERIODS.map((p) => (
          <button
            key={p.id}
            onClick={() => setPeriod(p.id)}
            className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              period === p.id
                ? 'bg-white text-orange-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Overview" actions={periodActions} />

      {error && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-red-600 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          Failed to load dashboard data. <button onClick={() => { setError(null); fetchData(); }} className="underline font-medium cursor-pointer">Retry</button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Total Leads"
          value={metrics?.total_leads ?? '\u2014'}
          icon={Users}
          color="brand"
        />
        <StatCard
          label="Booked"
          value={metrics?.total_booked ?? '\u2014'}
          deltaLabel={
            metrics
              ? `${(metrics.conversion_rate * 100).toFixed(1)}% conversion`
              : undefined
          }
          icon={CalendarCheck}
          color="green"
        />
        <StatCard
          label="Avg Response"
          value={hasResponseData ? `${avgResponseSec}s` : '\u2014'}
          icon={Timer}
          color={avgResponseColor}
        />
        <StatCard
          label="Under 60s"
          value={
            metrics
              ? `${metrics.leads_under_60s_pct.toFixed(0)}%`
              : '\u2014'
          }
          deltaLabel={
            metrics
              ? `${metrics.leads_under_60s} of ${metrics.total_leads}`
              : ''
          }
          icon={Gauge}
          color="green"
        />
      </div>

      {/* Charts row */}
      <div className="grid lg:grid-cols-2 gap-6">
        <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-5">
            <Clock className="w-4 h-4 text-gray-400" strokeWidth={1.75} />
            <h3 className="text-lg font-semibold text-gray-900">
              Response Time Distribution
            </h3>
          </div>
          <ResponseTimeChart
            data={metrics?.response_time_distribution || []}
          />
        </div>

        <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-5">
            <PieChart className="w-4 h-4 text-gray-400" strokeWidth={1.75} />
            <h3 className="text-lg font-semibold text-gray-900">
              Leads by Source
            </h3>
          </div>
          <SourceBreakdown data={metrics?.leads_by_source || {}} />
        </div>
      </div>

      {/* Leads per day */}
      {metrics?.leads_by_day?.length > 0 && (
        <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-5">
            <TrendingUp
              className="w-4 h-4 text-gray-400"
              strokeWidth={1.75}
            />
            <h3 className="text-lg font-semibold text-gray-900">
              Leads Per Day
            </h3>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={metrics.leads_by_day}
                margin={{ top: 0, right: 0, bottom: 0, left: -20 }}
              >
                <defs>
                  <linearGradient
                    id="leadGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="5%"
                      stopColor="#f97316"
                      stopOpacity={0.12}
                    />
                    <stop
                      offset="95%"
                      stopColor="#f97316"
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#f3f4f6"
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  cursor={{ stroke: '#e5e7eb' }}
                />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#f97316"
                  fill="url(#leadGradient)"
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="booked"
                  stroke="#10b981"
                  fill="none"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Activity feed */}
      <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-5">
          <Activity className="w-4 h-4 text-gray-400" strokeWidth={1.75} />
          <h3 className="text-lg font-semibold text-gray-900">
            Recent Activity
          </h3>
        </div>
        <div className="space-y-0.5 max-h-80 overflow-y-auto">
          {activity.length === 0 && (
            <p className="text-sm text-gray-400 py-4">No recent activity</p>
          )}
          {activity.map((event, i) => (
            <div
              key={event.id || `${event.type}-${event.timestamp}-${i}`}
              className="flex items-start gap-3 text-sm py-2.5 rounded-lg hover:bg-gray-50/50 px-3 -mx-3 transition-colors group"
            >
              <div className="relative flex-shrink-0 mt-2">
                <div
                  className={`w-2 h-2 rounded-full ${
                    ACTIVITY_DOT_COLORS[event.type] || 'bg-gray-300'
                  }`}
                />
                {i < activity.length - 1 && (
                  <div className="absolute top-3 left-1/2 -translate-x-1/2 w-px h-6 bg-gray-200" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="truncate text-gray-600 group-hover:text-gray-900 transition-colors">
                  {event.message}
                </p>
                <p className="text-xs mt-0.5 text-gray-400">
                  {formatDistanceToNow(new Date(event.timestamp), {
                    addSuffix: true,
                  })}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
