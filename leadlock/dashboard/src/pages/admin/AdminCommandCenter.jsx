import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import {
  Radio, Activity, Mail, Eye, MousePointer, MessageSquare,
  AlertTriangle, UserMinus, Zap, DollarSign, Users,
  Shield, BarChart3, MapPin, Globe, ChevronDown, ChevronUp,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import PageHeader from '../../components/ui/PageHeader';
import StatCard from '../../components/ui/StatCard';
import Badge from '../../components/ui/Badge';
import StatusDot from '../../components/ui/StatusDot';
import EmptyState from '../../components/ui/EmptyState';

const REFRESH_INTERVAL_MS = 30_000;

const ACTIVITY_CONFIG = {
  email_sent:       { color: 'text-blue-600',    bg: 'bg-blue-50',    icon: Mail },
  email_opened:     { color: 'text-emerald-600', bg: 'bg-emerald-50', icon: Eye },
  email_clicked:    { color: 'text-orange-600',  bg: 'bg-orange-50',  icon: MousePointer },
  email_replied:    { color: 'text-orange-600',  bg: 'bg-orange-50',  icon: MessageSquare },
  email_bounced:    { color: 'text-red-600',     bg: 'bg-red-50',     icon: AlertTriangle },
  scrape_completed: { color: 'text-gray-600',    bg: 'bg-gray-100',   icon: Globe },
  unsubscribed:     { color: 'text-amber-600',   bg: 'bg-amber-50',   icon: UserMinus },
};

const HEALTH_BADGE_VARIANT = {
  healthy: 'success',
  warning: 'warning',
  unhealthy: 'danger',
  unknown: 'neutral',
};

const HEALTH_DOT_COLOR = {
  healthy: 'green',
  warning: 'yellow',
  unhealthy: 'red',
  unknown: 'gray',
};

const FUNNEL_STAGES = [
  { key: 'cold',           label: 'Cold',           color: 'bg-gray-400' },
  { key: 'contacted',      label: 'Contacted',      color: 'bg-blue-500' },
  { key: 'demo_scheduled', label: 'Demo Scheduled', color: 'bg-orange-400' },
  { key: 'demo_completed', label: 'Demo Completed', color: 'bg-orange-500' },
  { key: 'proposal_sent',  label: 'Proposal Sent',  color: 'bg-amber-500' },
  { key: 'won',            label: 'Won',            color: 'bg-emerald-500' },
  { key: 'lost',           label: 'Lost',           color: 'bg-red-400' },
];

function formatAge(seconds) {
  if (seconds == null) return '\u2014';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function formatDisplayName(name) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function WorkerStatusBar({ workers }) {
  const entries = Object.entries(workers || {});
  if (entries.length === 0) return null;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {entries.map(([name, info]) => {
        const variant = HEALTH_BADGE_VARIANT[info.health] || 'neutral';
        return (
          <Badge key={name} variant={variant} size="sm">
            <StatusDot color={HEALTH_DOT_COLOR[info.health] || 'gray'} />
            <span className="ml-1.5">{formatDisplayName(name)}</span>
            <span className="ml-1 text-gray-400 font-mono">{formatAge(info.age_seconds)}</span>
            {info.paused && (
              <span className="ml-1 text-amber-600 uppercase text-[10px] font-bold">Paused</span>
            )}
          </Badge>
        );
      })}
    </div>
  );
}

function SystemInfoBar({ system }) {
  if (!system) return null;

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-5 shadow-sm mb-6">
      <div className="mb-3">
        <WorkerStatusBar workers={system.workers} />
      </div>
      <div className="flex flex-wrap items-center gap-5 text-xs">
        <div className="flex items-center gap-1.5">
          <StatusDot color={system.send_window?.is_active ? 'green' : 'gray'} />
          <span className={`font-semibold ${system.send_window?.is_active ? 'text-emerald-700' : 'text-gray-500'}`}>
            {system.send_window?.is_active ? 'LIVE' : 'PAUSED'}
          </span>
          <span className="text-gray-400">{system.send_window?.label || 'Not configured'}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <DollarSign className="w-3.5 h-3.5 text-gray-400" />
          <span className="font-medium text-gray-700 font-mono">
            ${(system.budget?.used_this_month ?? 0).toFixed(2)} / ${system.budget?.monthly_limit}
          </span>
          <span className={`font-semibold ${(system.budget?.pct_used ?? 0) > 80 ? 'text-amber-600' : 'text-gray-400'}`}>
            ({system.budget?.pct_used ?? 0}%)
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Zap className={`w-3.5 h-3.5 ${system.engine_active ? 'text-emerald-500' : 'text-red-400'}`} />
          <span className={`font-semibold ${system.engine_active ? 'text-emerald-700' : 'text-red-600'}`}>
            Engine {system.engine_active ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>
    </div>
  );
}

function PipelineFunnel({ funnel }) {
  const funnelMax = Math.max(...FUNNEL_STAGES.map((s) => funnel?.[s.key] || 0), 1);

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
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
  );
}

function ActivityFeed({ activity }) {
  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <Activity className="w-3.5 h-3.5" /> Live Activity
      </h2>
      <div className="space-y-0.5 max-h-[320px] overflow-y-auto pr-1">
        {(activity || []).length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">No recent activity</p>
        )}
        {(activity || []).map((evt, i) => {
          const cfg = ACTIVITY_CONFIG[evt.type] || ACTIVITY_CONFIG.email_sent;
          const Icon = cfg.icon;
          const ts = evt.timestamp ? new Date(evt.timestamp) : null;
          const timeStr = ts ? ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
          return (
            <div key={i} className="flex items-start gap-2.5 py-2 border-b border-gray-100 last:border-0">
              <div className={`w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${cfg.bg}`}>
                <Icon className={`w-3 h-3 ${cfg.color}`} strokeWidth={2} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-600 truncate">
                  {evt.prospect_name && <span className="font-medium text-gray-900">{evt.prospect_name}</span>}
                  {evt.prospect_name && ' \u2014 '}
                  {evt.detail}
                </p>
              </div>
              <span className="text-xs text-gray-400 flex-shrink-0 font-mono">{timeStr}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SequenceChart({ sequencePerformance }) {
  const stepChartData = (sequencePerformance || []).map((s) => ({
    name: `Step ${(s.step || 0) + 1}`,
    'Open %': s.open_rate,
    'Reply %': s.reply_rate,
  }));

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <BarChart3 className="w-3.5 h-3.5" /> Sequence Step Performance
      </h2>
      {stepChartData.length > 0 ? (
        <>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={stepChartData} barGap={4}>
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} unit="%" />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 12, border: '1px solid #e5e7eb', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}
                formatter={(v) => `${v}%`}
              />
              <Bar dataKey="Open %" fill="#fb923c" radius={[6, 6, 0, 0]} />
              <Bar dataKey="Reply %" fill="#10b981" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-3 space-y-1">
            {sequencePerformance.map((s) => (
              <div key={s.step} className="flex items-center justify-between text-xs text-gray-600 px-1">
                <span className="font-medium">Step {(s.step || 0) + 1}</span>
                <span className="font-mono">{s.sent} sent</span>
                <span className="font-mono">{s.open_rate}% open</span>
                <span className="font-mono">{s.reply_rate}% reply</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="text-xs text-gray-400 text-center py-8">No sequence data yet</p>
      )}
    </div>
  );
}

function AlertsPanel({ alerts }) {
  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
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
        {(alerts || []).map((alert, i) => {
          const borderColor = alert.severity === 'critical' ? 'border-l-red-500'
            : alert.severity === 'warning' ? 'border-l-amber-500'
            : 'border-l-blue-500';
          const variant = alert.severity === 'critical' ? 'danger'
            : alert.severity === 'warning' ? 'warning'
            : 'info';
          return (
            <div key={i} className={`flex items-start gap-3 p-3 rounded-xl border border-gray-200/60 border-l-4 ${borderColor}`}>
              <Badge variant={variant} size="sm">
                {alert.severity}
              </Badge>
              <p className="text-sm text-gray-600 flex-1">{alert.message}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GeoPerformanceTable({ geoPerformance }) {
  if ((geoPerformance || []).length === 0) return null;

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <MapPin className="w-3.5 h-3.5" /> Geographic Performance
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50/80 border-b border-gray-200/60">
              <th className="text-left py-3 px-3 text-xs font-medium text-gray-500 uppercase tracking-wider">City</th>
              <th className="text-left py-3 px-3 text-xs font-medium text-gray-500 uppercase tracking-wider">State</th>
              <th className="text-right py-3 px-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Prospects</th>
              <th className="text-right py-3 px-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Emails Sent</th>
              <th className="text-right py-3 px-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Open Rate</th>
              <th className="text-right py-3 px-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Reply Rate</th>
            </tr>
          </thead>
          <tbody>
            {geoPerformance.map((row, i) => (
              <tr key={i} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/50 transition-colors">
                <td className="py-3 px-3 font-medium text-gray-900">{row.city || '\u2014'}</td>
                <td className="py-3 px-3 text-gray-500">{row.state || '\u2014'}</td>
                <td className="py-3 px-3 text-right font-mono text-gray-900">{row.prospects}</td>
                <td className="py-3 px-3 text-right font-mono text-gray-900">{row.emails_sent}</td>
                <td className="py-3 px-3 text-right font-mono text-gray-900">{row.open_rate}%</td>
                <td className="py-3 px-3 text-right font-mono text-gray-900">{row.reply_rate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScraperStatus({ scraper }) {
  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <Globe className="w-3.5 h-3.5" /> Scraper Status
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wider">Total Prospects</p>
          <p className="text-xl font-bold font-mono text-gray-900 mt-1">{scraper?.total_prospects || 0}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wider">Scraped Today</p>
          <p className="text-xl font-bold font-mono text-gray-900 mt-1">{scraper?.scraped_today || 0}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wider">New Today</p>
          <p className="text-xl font-bold font-mono text-emerald-600 mt-1">{scraper?.new_today || 0}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wider">Dupes Today</p>
          <p className="text-xl font-bold font-mono text-gray-500 mt-1">{scraper?.dupes_today || 0}</p>
        </div>
      </div>
      {(scraper?.locations || []).length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {scraper.locations.map((loc, i) => (
            <span key={i} className="text-xs px-2.5 py-1 rounded-lg bg-gray-50 text-gray-600 font-medium border border-gray-200/60">
              {typeof loc === 'string' ? loc : `${loc.city}, ${loc.state}`}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function RecentEmails({ recentEmails, expandedEmail, setExpandedEmail }) {
  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <Mail className="w-3.5 h-3.5" /> Recent Emails
      </h2>
      {(recentEmails || []).length === 0 ? (
        <p className="text-xs text-gray-400 text-center py-6">No emails sent yet</p>
      ) : (
        <div className="space-y-1.5">
          {recentEmails.map((email) => {
            const isExpanded = expandedEmail === email.id;
            const ts = email.sent_at ? new Date(email.sent_at) : null;
            return (
              <div key={email.id} className="border border-gray-200/60 rounded-xl overflow-hidden">
                <button
                  onClick={() => setExpandedEmail(isExpanded ? null : email.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50/50 transition-colors cursor-pointer"
                >
                  <StatusDot
                    color={email.bounced_at ? 'red' : email.opened_at ? 'green' : 'gray'}
                  />
                  <span className="text-sm font-medium text-gray-900 w-32 truncate flex-shrink-0">
                    {email.prospect_name}
                  </span>
                  <span className="text-sm text-gray-500 flex-1 truncate">
                    {email.subject || `Step ${(email.step || 0) + 1}`}
                  </span>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Badge variant="neutral" size="sm">
                      Step {(email.step || 0) + 1}
                    </Badge>
                    <span className="text-xs text-gray-400 font-mono">
                      {ts ? ts.toLocaleDateString([], { month: 'short', day: 'numeric' }) : ''}
                    </span>
                    {isExpanded ? (
                      <ChevronUp className="w-3.5 h-3.5 text-gray-400" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                    )}
                  </div>
                </button>
                {isExpanded && (
                  <div className="px-4 pb-4 pt-2 border-t border-gray-100 bg-gray-50/50">
                    <div className="flex gap-3 mb-2 text-xs text-gray-400">
                      {email.sent_at && <span>Sent: <span className="font-mono">{new Date(email.sent_at).toLocaleString()}</span></span>}
                      {email.opened_at && <span className="text-emerald-600">Opened: <span className="font-mono">{new Date(email.opened_at).toLocaleString()}</span></span>}
                      {email.clicked_at && <span className="text-orange-600">Clicked: <span className="font-mono">{new Date(email.clicked_at).toLocaleString()}</span></span>}
                      {email.bounced_at && <span className="text-red-600">Bounced</span>}
                    </div>
                    <p className="text-sm text-gray-500 leading-relaxed">{email.body_preview || 'No preview available'}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="min-h-screen bg-[#FAFAFA] space-y-6">
      <div className="h-8 w-56 rounded-lg bg-gray-100 animate-pulse" />
      <div className="h-20 rounded-2xl bg-gray-100 animate-pulse" />
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-28 rounded-2xl bg-gray-100 animate-pulse" />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="h-72 rounded-2xl bg-gray-100 animate-pulse" />
        <div className="h-72 rounded-2xl bg-gray-100 animate-pulse" />
      </div>
    </div>
  );
}

function computeDelta(current, previous) {
  if (!previous || previous === 0) return undefined;
  return Math.round(((current - previous) / previous) * 100);
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

  if (loading) return <LoadingSkeleton />;

  if (!data) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <EmptyState
          icon={AlertTriangle}
          title="Unable to load data"
          description="Failed to load command center data. Please try again."
        />
      </div>
    );
  }

  const { system, email_pipeline, funnel, scraper, sequence_performance, geo_performance, recent_emails, activity, alerts } = data;
  const today = email_pipeline?.today || {};
  const period = email_pipeline?.period_30d || {};
  const prev = email_pipeline?.prev_30d || {};

  const subtitleText = lastUpdated
    ? `Live \u00b7 Updated ${lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    : 'Live';

  return (
    <div className="min-h-screen bg-[#FAFAFA] space-y-6">
      <PageHeader
        title="Command Center"
        subtitle={subtitleText}
        actions={
          <div className="flex items-center gap-2">
            <StatusDot color="green" />
            <span className="text-xs font-medium text-gray-400">Auto-refresh 30s</span>
          </div>
        }
      />

      <SystemInfoBar system={system} />

      {/* Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          label="Sent Today"
          value={`${today.sent || 0} / ${today.daily_limit || 50}`}
          icon={Mail}
          color="brand"
        />
        <StatCard
          label="Open Rate"
          value={`${period.open_rate || 0}%`}
          delta={computeDelta(period.open_rate, prev.open_rate)}
          deltaLabel="vs prev 30d"
          icon={Eye}
          color="green"
        />
        <StatCard
          label="Click Rate"
          value={`${period.click_rate || 0}%`}
          delta={computeDelta(period.click_rate, prev.click_rate)}
          deltaLabel="vs prev 30d"
          icon={MousePointer}
          color="brand"
        />
        <StatCard
          label="Reply Rate"
          value={`${period.reply_rate || 0}%`}
          delta={computeDelta(period.reply_rate, prev.reply_rate)}
          deltaLabel="vs prev 30d"
          icon={MessageSquare}
          color="brand"
        />
        <StatCard
          label="Bounce Rate"
          value={`${period.bounce_rate || 0}%`}
          delta={computeDelta(period.bounce_rate, prev.bounce_rate)}
          deltaLabel="vs prev 30d"
          icon={AlertTriangle}
          color="red"
        />
        <StatCard
          label="Unsubs Today"
          value={today.unsubscribed || 0}
          icon={UserMinus}
          color="yellow"
        />
      </div>

      {/* Pipeline + Activity Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PipelineFunnel funnel={funnel} />
        <ActivityFeed activity={activity} />
      </div>

      {/* Sequence Performance + Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SequenceChart sequencePerformance={sequence_performance} />
        <AlertsPanel alerts={alerts} />
      </div>

      {/* Geographic Performance */}
      <GeoPerformanceTable geoPerformance={geo_performance} />

      {/* Scraper Status */}
      <ScraperStatus scraper={scraper} />

      {/* Recent Emails */}
      <RecentEmails
        recentEmails={recent_emails}
        expandedEmail={expandedEmail}
        setExpandedEmail={setExpandedEmail}
      />
    </div>
  );
}
