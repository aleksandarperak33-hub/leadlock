import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import {
  Radio, Activity, Mail, Eye, MousePointer, MessageSquare,
  AlertTriangle, Search, UserMinus, ArrowUpRight, ArrowDownRight,
  Minus, ChevronDown, ChevronUp, Zap, DollarSign, Users,
  Clock, Shield, BarChart3, MapPin, Globe,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const REFRESH_INTERVAL_MS = 30_000;

const ACTIVITY_CONFIG = {
  email_sent:      { color: 'text-blue-600',    bg: 'bg-blue-50',    icon: Mail },
  email_opened:    { color: 'text-emerald-600',  bg: 'bg-emerald-50', icon: Eye },
  email_clicked:   { color: 'text-indigo-600',   bg: 'bg-indigo-50',  icon: MousePointer },
  email_replied:   { color: 'text-violet-600',   bg: 'bg-violet-50',  icon: MessageSquare },
  email_bounced:   { color: 'text-red-600',      bg: 'bg-red-50',     icon: AlertTriangle },
  scrape_completed:{ color: 'text-gray-600',     bg: 'bg-gray-100',   icon: Search },
  unsubscribed:    { color: 'text-amber-600',    bg: 'bg-amber-50',   icon: UserMinus },
};

const HEALTH_DOT = {
  healthy:  'bg-emerald-500',
  warning:  'bg-amber-500',
  unhealthy:'bg-red-500',
  unknown:  'bg-gray-400',
};

const FUNNEL_STAGES = [
  { key: 'cold',           label: 'Cold',           color: 'bg-gray-400' },
  { key: 'contacted',      label: 'Contacted',      color: 'bg-blue-500' },
  { key: 'demo_scheduled', label: 'Demo Scheduled', color: 'bg-violet-500' },
  { key: 'demo_completed', label: 'Demo Completed', color: 'bg-purple-500' },
  { key: 'proposal_sent',  label: 'Proposal Sent',  color: 'bg-indigo-500' },
  { key: 'won',            label: 'Won',            color: 'bg-emerald-500' },
  { key: 'lost',           label: 'Lost',           color: 'bg-red-400' },
];

function TrendArrow({ current, previous }) {
  if (!previous || previous === 0) return <Minus className="w-3 h-3 text-gray-400" />;
  const diff = current - previous;
  if (Math.abs(diff) < 0.5) return <Minus className="w-3 h-3 text-gray-400" />;
  if (diff > 0) return <ArrowUpRight className="w-3.5 h-3.5 text-emerald-600" />;
  return <ArrowDownRight className="w-3.5 h-3.5 text-red-500" />;
}

function HealthDot({ health, pulse = false }) {
  const color = HEALTH_DOT[health] || HEALTH_DOT.unknown;
  return (
    <span className="relative flex h-2 w-2">
      {pulse && health === 'healthy' && (
        <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${color} opacity-75`} />
      )}
      <span className={`relative inline-flex rounded-full h-2 w-2 ${color}`} />
    </span>
  );
}

function WorkerBadge({ name, info }) {
  const displayName = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const ageLabel = info.age_seconds != null
    ? info.age_seconds < 60 ? `${info.age_seconds}s`
      : info.age_seconds < 3600 ? `${Math.floor(info.age_seconds / 60)}m`
        : `${Math.floor(info.age_seconds / 3600)}h`
    : '—';

  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white border border-gray-200 text-xs">
      <HealthDot health={info.health} pulse />
      <span className="font-medium text-gray-700">{displayName}</span>
      <span className="text-gray-400">{ageLabel}</span>
      {info.paused && <span className="text-[10px] font-semibold text-amber-600 uppercase">Paused</span>}
    </div>
  );
}

function MetricCard({ label, value, sub, trend, icon: Icon, color = 'gray' }) {
  const colorMap = {
    blue: { bg: 'bg-blue-50', text: 'text-blue-600' },
    emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
    indigo: { bg: 'bg-indigo-50', text: 'text-indigo-600' },
    violet: { bg: 'bg-violet-50', text: 'text-violet-600' },
    red: { bg: 'bg-red-50', text: 'text-red-600' },
    amber: { bg: 'bg-amber-50', text: 'text-amber-600' },
    gray: { bg: 'bg-gray-100', text: 'text-gray-600' },
  };
  const c = colorMap[color] || colorMap.gray;

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4 card-accent-top hover:shadow-md hover:-translate-y-0.5 transition-all duration-200">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">{label}</span>
        {Icon && (
          <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${c.bg}`}>
            <Icon className={`w-3.5 h-3.5 ${c.text}`} strokeWidth={2} />
          </div>
        )}
      </div>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold font-mono text-gray-900">{value}</span>
        {trend && <span className="mb-0.5">{trend}</span>}
      </div>
      {sub && <p className="text-[11px] text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function SeverityBadge({ severity }) {
  const map = {
    critical: 'bg-red-100 text-red-700 border-red-200',
    warning: 'bg-amber-100 text-amber-700 border-amber-200',
    info: 'bg-blue-100 text-blue-700 border-blue-200',
  };
  return (
    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border ${map[severity] || map.info}`}>
      {severity}
    </span>
  );
}

export default function AdminCommandCenter() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [expandedEmail, setExpandedEmail] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await api.getCommandCenter();
      setData(result);
      setLastUpdated(new Date());
    } catch (e) {
      console.error('Command center fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-4 animate-page-in">
        <div className="h-6 w-56 rounded bg-gray-100 animate-pulse" />
        <div className="h-16 rounded-xl bg-gray-100 animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-24 rounded-xl bg-gray-100 animate-pulse" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="h-72 rounded-xl bg-gray-100 animate-pulse" />
          <div className="h-72 rounded-xl bg-gray-100 animate-pulse" />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-20 text-gray-400">
        <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
        <p className="text-sm">Failed to load command center data</p>
      </div>
    );
  }

  const { system, email_pipeline, funnel, scraper, sequence_performance, geo_performance, recent_emails, activity, alerts } = data;
  const today = email_pipeline?.today || {};
  const period = email_pipeline?.period_30d || {};
  const prev = email_pipeline?.prev_30d || {};
  const funnelMax = Math.max(...FUNNEL_STAGES.map(s => funnel?.[s.key] || 0), 1);

  const stepChartData = (sequence_performance || []).map(s => ({
    name: `Step ${(s.step || 0) + 1}`,
    'Open %': s.open_rate,
    'Reply %': s.reply_rate,
  }));

  return (
    <div className="space-y-5 animate-page-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-gradient-to-br from-violet-500 to-purple-600 shadow-md shadow-violet-500/20">
            <Radio className="w-4.5 h-4.5 text-white" strokeWidth={2.5} />
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-gray-900">Command Center</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="text-xs font-medium text-gray-400">Live</span>
          {lastUpdated && (
            <span className="text-[11px] text-gray-400">
              Updated {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>

      {/* System Status Bar */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          {Object.entries(system?.workers || {}).map(([name, info]) => (
            <WorkerBadge key={name} name={name} info={info} />
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <HealthDot health={system?.send_window?.is_active ? 'healthy' : 'unknown'} pulse />
            <span className={`font-semibold ${system?.send_window?.is_active ? 'text-emerald-700' : 'text-gray-500'}`}>
              {system?.send_window?.is_active ? 'LIVE' : 'PAUSED'}
            </span>
            <span className="text-gray-400">— {system?.send_window?.label || 'Not configured'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <DollarSign className="w-3.5 h-3.5 text-gray-400" />
            <span className="font-medium text-gray-700">
              ${system?.budget?.used_this_month?.toFixed(2)} / ${system?.budget?.monthly_limit}
            </span>
            <span className={`font-semibold ${(system?.budget?.pct_used || 0) > 80 ? 'text-amber-600' : 'text-gray-400'}`}>
              ({system?.budget?.pct_used}%)
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Zap className={`w-3.5 h-3.5 ${system?.engine_active ? 'text-emerald-500' : 'text-red-400'}`} />
            <span className={`font-semibold ${system?.engine_active ? 'text-emerald-700' : 'text-red-600'}`}>
              Engine {system?.engine_active ? 'Active' : 'Inactive'}
            </span>
          </div>
        </div>
      </div>

      {/* Email Metrics — Today */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          label="Sent Today"
          value={`${today.sent || 0} / ${today.daily_limit || 50}`}
          icon={Mail}
          color="blue"
        />
        <MetricCard
          label="Open Rate"
          value={`${period.open_rate || 0}%`}
          trend={<TrendArrow current={period.open_rate} previous={prev.open_rate} />}
          sub="30-day"
          icon={Eye}
          color="emerald"
        />
        <MetricCard
          label="Click Rate"
          value={`${period.click_rate || 0}%`}
          trend={<TrendArrow current={period.click_rate} previous={prev.click_rate} />}
          sub="30-day"
          icon={MousePointer}
          color="indigo"
        />
        <MetricCard
          label="Reply Rate"
          value={`${period.reply_rate || 0}%`}
          trend={<TrendArrow current={period.reply_rate} previous={prev.reply_rate} />}
          sub="30-day"
          icon={MessageSquare}
          color="violet"
        />
        <MetricCard
          label="Bounce Rate"
          value={`${period.bounce_rate || 0}%`}
          trend={<TrendArrow current={prev.bounce_rate} previous={period.bounce_rate} />}
          sub="30-day"
          icon={AlertTriangle}
          color="red"
        />
        <MetricCard
          label="Unsubs Today"
          value={today.unsubscribed || 0}
          icon={UserMinus}
          color="amber"
        />
      </div>

      {/* Middle Row: Funnel + Activity Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Funnel */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 card-accent-top">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
            <Users className="w-3.5 h-3.5" /> Prospect Pipeline
          </h2>
          <div className="space-y-2.5">
            {FUNNEL_STAGES.map(({ key, label, color }) => {
              const count = funnel?.[key] || 0;
              const pct = funnelMax > 0 ? (count / funnelMax) * 100 : 0;
              return (
                <div key={key} className="flex items-center gap-3">
                  <span className="text-xs font-medium text-gray-600 w-28 truncate">{label}</span>
                  <div className="flex-1 h-6 bg-gray-100 rounded-md overflow-hidden">
                    <div
                      className={`h-full ${color} rounded-md transition-all duration-500`}
                      style={{ width: `${Math.max(pct, 2)}%` }}
                    />
                  </div>
                  <span className="text-xs font-bold font-mono text-gray-700 w-10 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Activity Feed */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 card-accent-top">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
            <Activity className="w-3.5 h-3.5" /> Live Activity
          </h2>
          <div className="space-y-1.5 max-h-[320px] overflow-y-auto pr-1">
            {(activity || []).length === 0 && (
              <p className="text-xs text-gray-400 text-center py-4">No recent activity</p>
            )}
            {(activity || []).map((evt, i) => {
              const cfg = ACTIVITY_CONFIG[evt.type] || ACTIVITY_CONFIG.email_sent;
              const Icon = cfg.icon;
              const ts = evt.timestamp ? new Date(evt.timestamp) : null;
              const timeStr = ts ? ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
              return (
                <div key={i} className="flex items-start gap-2.5 py-1.5 border-b border-gray-50 last:border-0">
                  <div className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5 ${cfg.bg}`}>
                    <Icon className={`w-3 h-3 ${cfg.color}`} strokeWidth={2} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-700 truncate">
                      {evt.prospect_name && <span className="font-semibold">{evt.prospect_name}</span>}
                      {evt.prospect_name && ' — '}
                      {evt.detail}
                    </p>
                  </div>
                  <span className="text-[10px] text-gray-400 flex-shrink-0 tabular-nums">{timeStr}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Sequence Performance + Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Sequence Steps Chart */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 card-accent-top">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
            <BarChart3 className="w-3.5 h-3.5" /> Sequence Step Performance
          </h2>
          {stepChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={stepChartData} barGap={4}>
                <XAxis dataKey="name" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} unit="%" />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                  formatter={(v) => `${v}%`}
                />
                <Bar dataKey="Open %" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Reply %" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-gray-400 text-center py-8">No sequence data yet</p>
          )}
          {/* Step detail table */}
          {(sequence_performance || []).length > 0 && (
            <div className="mt-3 space-y-1">
              {sequence_performance.map(s => (
                <div key={s.step} className="flex items-center justify-between text-xs text-gray-600 px-1">
                  <span className="font-medium">Step {(s.step || 0) + 1}</span>
                  <span className="tabular-nums">{s.sent} sent</span>
                  <span className="tabular-nums">{s.open_rate}% open</span>
                  <span className="tabular-nums">{s.reply_rate}% reply</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Alerts */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 card-accent-top">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
            <Shield className="w-3.5 h-3.5" /> Alerts & Issues
          </h2>
          <div className="space-y-2.5">
            {(alerts || []).length === 0 && (
              <div className="text-center py-8">
                <div className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-2">
                  <Zap className="w-5 h-5 text-emerald-500" />
                </div>
                <p className="text-xs text-gray-400">All systems nominal</p>
              </div>
            )}
            {(alerts || []).map((alert, i) => (
              <div
                key={i}
                className={`flex items-start gap-3 p-3 rounded-lg border ${
                  alert.severity === 'critical' ? 'bg-red-50 border-red-200' :
                  alert.severity === 'warning' ? 'bg-amber-50 border-amber-200' :
                  'bg-blue-50 border-blue-200'
                }`}
              >
                <SeverityBadge severity={alert.severity} />
                <p className="text-xs text-gray-700 flex-1">{alert.message}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Geographic Performance */}
      {(geo_performance || []).length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 card-accent-top">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
            <MapPin className="w-3.5 h-3.5" /> Geographic Performance
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-2 px-2 font-semibold text-gray-500">City</th>
                  <th className="text-left py-2 px-2 font-semibold text-gray-500">State</th>
                  <th className="text-right py-2 px-2 font-semibold text-gray-500">Prospects</th>
                  <th className="text-right py-2 px-2 font-semibold text-gray-500">Emails Sent</th>
                  <th className="text-right py-2 px-2 font-semibold text-gray-500">Open Rate</th>
                  <th className="text-right py-2 px-2 font-semibold text-gray-500">Reply Rate</th>
                </tr>
              </thead>
              <tbody>
                {geo_performance.map((row, i) => (
                  <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                    <td className="py-2 px-2 font-medium text-gray-700">{row.city || '—'}</td>
                    <td className="py-2 px-2 text-gray-500">{row.state || '—'}</td>
                    <td className="py-2 px-2 text-right font-mono text-gray-700">{row.prospects}</td>
                    <td className="py-2 px-2 text-right font-mono text-gray-700">{row.emails_sent}</td>
                    <td className="py-2 px-2 text-right font-mono text-gray-700">{row.open_rate}%</td>
                    <td className="py-2 px-2 text-right font-mono text-gray-700">{row.reply_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Scraper Status */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 card-accent-top">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
          <Globe className="w-3.5 h-3.5" /> Scraper Status
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p className="text-[11px] text-gray-400 uppercase tracking-wider">Total Prospects</p>
            <p className="text-xl font-bold font-mono text-gray-900">{scraper?.total_prospects || 0}</p>
          </div>
          <div>
            <p className="text-[11px] text-gray-400 uppercase tracking-wider">Scraped Today</p>
            <p className="text-xl font-bold font-mono text-gray-900">{scraper?.scraped_today || 0}</p>
          </div>
          <div>
            <p className="text-[11px] text-gray-400 uppercase tracking-wider">New Today</p>
            <p className="text-xl font-bold font-mono text-emerald-600">{scraper?.new_today || 0}</p>
          </div>
          <div>
            <p className="text-[11px] text-gray-400 uppercase tracking-wider">Dupes Today</p>
            <p className="text-xl font-bold font-mono text-gray-500">{scraper?.dupes_today || 0}</p>
          </div>
        </div>
        {(scraper?.locations || []).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {scraper.locations.map((loc, i) => (
              <span key={i} className="text-[11px] px-2 py-1 rounded-md bg-gray-100 text-gray-600 font-medium">
                {typeof loc === 'string' ? loc : `${loc.city}, ${loc.state}`}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Recent Emails */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 card-accent-top">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
          <Mail className="w-3.5 h-3.5" /> Recent Emails
        </h2>
        {(recent_emails || []).length === 0 ? (
          <p className="text-xs text-gray-400 text-center py-6">No emails sent yet</p>
        ) : (
          <div className="space-y-1">
            {recent_emails.map((email) => {
              const isExpanded = expandedEmail === email.id;
              const ts = email.sent_at ? new Date(email.sent_at) : null;
              return (
                <div key={email.id} className="border border-gray-100 rounded-lg overflow-hidden">
                  <button
                    onClick={() => setExpandedEmail(isExpanded ? null : email.id)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-gray-50/50 transition-colors cursor-pointer"
                  >
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {email.bounced_at ? (
                        <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                      ) : email.opened_at ? (
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      ) : (
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
                      )}
                    </div>
                    <span className="text-xs font-semibold text-gray-700 w-32 truncate flex-shrink-0">
                      {email.prospect_name}
                    </span>
                    <span className="text-xs text-gray-500 flex-1 truncate">
                      {email.subject || `Step ${(email.step || 0) + 1}`}
                    </span>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 font-medium">
                        Step {(email.step || 0) + 1}
                      </span>
                      <span className="text-[10px] text-gray-400 tabular-nums">
                        {ts ? ts.toLocaleDateString([], { month: 'short', day: 'numeric' }) : ''}
                      </span>
                      {isExpanded ? <ChevronUp className="w-3 h-3 text-gray-400" /> : <ChevronDown className="w-3 h-3 text-gray-400" />}
                    </div>
                  </button>
                  {isExpanded && (
                    <div className="px-3 pb-3 pt-1 border-t border-gray-100 bg-gray-50/50">
                      <div className="flex gap-3 mb-2 text-[10px] text-gray-400">
                        {email.sent_at && <span>Sent: {new Date(email.sent_at).toLocaleString()}</span>}
                        {email.opened_at && <span className="text-emerald-600">Opened: {new Date(email.opened_at).toLocaleString()}</span>}
                        {email.clicked_at && <span className="text-indigo-600">Clicked: {new Date(email.clicked_at).toLocaleString()}</span>}
                        {email.bounced_at && <span className="text-red-600">Bounced</span>}
                      </div>
                      <p className="text-xs text-gray-600 leading-relaxed">{email.body_preview || 'No preview available'}</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
