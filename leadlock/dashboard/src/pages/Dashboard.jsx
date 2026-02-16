import { useState, useEffect } from 'react';
import { api } from '../api/client';
import MetricCard from '../components/MetricCard';
import ResponseTimeChart from '../components/ResponseTimeChart';
import SourceBreakdown from '../components/SourceBreakdown';
import LiveIndicator from '../components/LiveIndicator';
import {
  Users, CalendarCheck, Timer, Gauge, Activity
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { formatDistanceToNow } from 'date-fns';

const PERIODS = ['7d', '30d', '90d'];

const ACTIVITY_DOT_COLORS = {
  booking_confirmed: 'bg-emerald-500',
  lead_created: 'bg-indigo-500',
  opt_out: 'bg-red-500',
};

const TOOLTIP_STYLE = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
  color: '#111827',
  fontSize: '12px',
  boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
  padding: '8px 12px',
};

export default function Dashboard() {
  const [period, setPeriod] = useState('7d');
  const [metrics, setMetrics] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [m, a] = await Promise.all([
        api.getMetrics(period),
        api.getActivity(20),
      ]);
      setMetrics(m);
      setActivity(a);
    } catch (e) {
      console.error('Failed to fetch dashboard data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [period]);

  const avgResponseSec = metrics ? (metrics.avg_response_time_ms / 1000).toFixed(1) : '\u2014';
  const responseColor = metrics?.avg_response_time_ms < 10000 ? 'green' :
                         metrics?.avg_response_time_ms < 60000 ? 'yellow' : 'red';

  if (loading && !metrics) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-40 rounded-lg bg-gray-100 animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-gray-100 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-gray-900">Overview</h1>
          <div className="mt-1.5"><LiveIndicator /></div>
        </div>
        <div className="flex rounded-lg p-0.5 bg-gray-100 border border-gray-200">
          {PERIODS.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-all cursor-pointer ${
                period === p
                  ? 'bg-white text-indigo-600 shadow-sm border border-gray-200'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard
          title="Total Leads"
          value={metrics?.total_leads ?? '\u2014'}
          icon={Users}
          color="brand"
          trend={12}
          trendLabel="vs prev"
        />
        <MetricCard
          title="Booked"
          value={metrics?.total_booked ?? '\u2014'}
          subtitle={metrics ? `${(metrics.conversion_rate * 100).toFixed(1)}% conversion` : ''}
          icon={CalendarCheck}
          color="green"
        />
        <MetricCard
          title="Avg Response"
          value={`${avgResponseSec}s`}
          icon={Timer}
          color={responseColor}
        />
        <MetricCard
          title="Under 60s"
          value={metrics ? `${metrics.leads_under_60s_pct.toFixed(0)}%` : '\u2014'}
          subtitle={metrics ? `${metrics.leads_under_60s} of ${metrics.total_leads}` : ''}
          icon={Gauge}
          color="green"
        />
      </div>

      {/* Charts row */}
      <div className="grid lg:grid-cols-2 gap-4 mb-6">
        <ResponseTimeChart data={metrics?.response_time_distribution || []} />
        <SourceBreakdown data={metrics?.leads_by_source || {}} />
      </div>

      {/* Leads per day */}
      {metrics?.leads_by_day?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 mb-6">
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-4 text-gray-500">
            Leads Per Day
          </h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={metrics.leads_by_day} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="leadGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: '#e5e7eb' }} />
                <Area type="monotone" dataKey="count" stroke="#6366f1" fill="url(#leadGradient)" strokeWidth={2} />
                <Area type="monotone" dataKey="booked" stroke="#10b981" fill="none" strokeWidth={1.5} strokeDasharray="4 4" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Activity feed */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-3.5 h-3.5 text-gray-400" strokeWidth={1.75} />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
            Recent Activity
          </h3>
        </div>
        <div className="space-y-1 max-h-80 overflow-y-auto">
          {activity.length === 0 && (
            <p className="text-sm text-gray-400">No recent activity</p>
          )}
          {activity.map((event, i) => (
            <div key={i} className="flex items-start gap-3 text-sm py-2 rounded-lg hover:bg-gray-50 px-2 -mx-2 transition-colors">
              <div className={`w-1.5 h-1.5 mt-[7px] rounded-full flex-shrink-0 ${
                ACTIVITY_DOT_COLORS[event.type] || 'bg-gray-400'
              }`} />
              <div className="flex-1 min-w-0">
                <p className="truncate text-gray-600">{event.message}</p>
                <p className="text-xs mt-0.5 text-gray-400">
                  {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
