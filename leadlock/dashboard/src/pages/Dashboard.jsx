import { useState, useEffect } from 'react';
import { api } from '../api/client';
import MetricCard from '../components/MetricCard';
import ResponseTimeChart from '../components/ResponseTimeChart';
import SourceBreakdown from '../components/SourceBreakdown';
import LiveIndicator from '../components/LiveIndicator';
import {
  Users, CalendarCheck, Timer, Gauge, Activity
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { formatDistanceToNow } from 'date-fns';

const PERIODS = ['7d', '30d', '90d'];

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
        <div className="h-8 w-48 bg-slate-800 rounded animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 bg-slate-900 border border-slate-800 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white">Dashboard</h1>
          <div className="mt-1"><LiveIndicator /></div>
        </div>
        <div className="flex bg-slate-800 rounded-lg p-0.5">
          {PERIODS.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                period === p ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

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

      <div className="grid lg:grid-cols-2 gap-4 mb-6">
        <ResponseTimeChart data={metrics?.response_time_distribution || []} />
        <SourceBreakdown data={metrics?.leads_by_source || {}} />
      </div>

      {metrics?.leads_by_day?.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 mb-6">
          <h3 className="text-sm font-medium text-slate-400 mb-4">Leads Per Day</h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={metrics.leads_by_day} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="leadGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#338dff" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#338dff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Area type="monotone" dataKey="count" stroke="#338dff" fill="url(#leadGradient)" strokeWidth={2} />
                <Area type="monotone" dataKey="booked" stroke="#10b981" fill="none" strokeWidth={2} strokeDasharray="4 4" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-4 h-4 text-slate-400" />
          <h3 className="text-sm font-medium text-slate-400">Recent Activity</h3>
        </div>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {activity.length === 0 && (
            <p className="text-slate-500 text-sm">No recent activity</p>
          )}
          {activity.map((event, i) => (
            <div key={i} className="flex items-start gap-3 text-sm">
              <div className={`w-2 h-2 mt-1.5 rounded-full flex-shrink-0 ${
                event.type === 'booking_confirmed' ? 'bg-emerald-400' :
                event.type === 'lead_created' ? 'bg-blue-400' :
                event.type === 'opt_out' ? 'bg-red-400' :
                'bg-slate-500'
              }`} />
              <div className="flex-1 min-w-0">
                <p className="text-slate-300 truncate">{event.message}</p>
                <p className="text-xs text-slate-500 mt-0.5">
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
