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
      <div className="space-y-4 animate-fade-up">
        <div className="h-6 w-40 rounded-lg animate-pulse" style={{ background: 'var(--surface-2)' }} />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 rounded-xl animate-pulse" style={{ background: 'var(--surface-1)' }} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Overview</h1>
          <div className="mt-1.5"><LiveIndicator /></div>
        </div>
        <div className="flex rounded-lg p-0.5 glass" style={{ border: '1px solid rgba(255, 255, 255, 0.06)' }}>
          {PERIODS.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className="px-3 py-1 text-[11px] font-medium rounded-md transition-all duration-200"
              style={{
                background: period === p ? 'var(--accent-muted)' : 'transparent',
                color: period === p ? 'var(--accent)' : 'var(--text-tertiary)',
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
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
      <div className="grid lg:grid-cols-2 gap-3 mb-6">
        <ResponseTimeChart data={metrics?.response_time_distribution || []} />
        <SourceBreakdown data={metrics?.leads_by_source || {}} />
      </div>

      {/* Leads per day */}
      {metrics?.leads_by_day?.length > 0 && (
        <div className="glass-card gradient-border p-5 mb-6">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>
            Leads Per Day
          </h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={metrics.leads_by_day} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="leadGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fill: '#555c72', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#555c72', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    background: 'rgba(15, 17, 24, 0.9)',
                    backdropFilter: 'blur(12px)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '10px',
                    color: '#edf0f7',
                    fontSize: '12px',
                    boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                  }}
                />
                <Area type="monotone" dataKey="count" stroke="var(--accent)" fill="url(#leadGradient)" strokeWidth={1.5} />
                <Area type="monotone" dataKey="booked" stroke="#34d399" fill="none" strokeWidth={1.5} strokeDasharray="4 4" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Activity feed */}
      <div className="glass-card gradient-border p-5">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} strokeWidth={1.75} />
          <h3 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
            Recent Activity
          </h3>
        </div>
        <div className="space-y-2.5 max-h-80 overflow-y-auto">
          {activity.length === 0 && (
            <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>No recent activity</p>
          )}
          {activity.map((event, i) => (
            <div key={i} className="flex items-start gap-3 text-[13px] py-1">
              <div className="w-1.5 h-1.5 mt-[7px] rounded-full flex-shrink-0" style={{
                background: event.type === 'booking_confirmed' ? '#34d399' :
                            event.type === 'lead_created' ? '#6366f1' :
                            event.type === 'opt_out' ? '#f87171' :
                            '#475569',
                boxShadow: event.type === 'booking_confirmed' ? '0 0 6px rgba(52, 211, 153, 0.5)' :
                           event.type === 'lead_created' ? '0 0 6px rgba(99, 102, 241, 0.5)' :
                           'none',
              }} />
              <div className="flex-1 min-w-0">
                <p className="truncate" style={{ color: 'var(--text-secondary)' }}>{event.message}</p>
                <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
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
