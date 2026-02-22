import { useState, useEffect } from 'react';
import { X, ChevronDown, ChevronRight } from 'lucide-react';
import {
  FlaskConical, Thermometer, RefreshCw, Factory, Share2,
  Search, Gift, Brain, HeartPulse, Sparkles,
} from 'lucide-react';
import { AreaChart, Area, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import { api } from '../../api/client';

const ICON_MAP = {
  'flask-conical': FlaskConical,
  'thermometer': Thermometer,
  'refresh-cw': RefreshCw,
  'factory': Factory,
  'share-2': Share2,
  'search': Search,
  'gift': Gift,
  'brain': Brain,
  'heart-pulse': HeartPulse,
};

const COLOR_ICON = {
  purple: 'text-purple-500', blue: 'text-blue-500', amber: 'text-amber-500',
  green: 'text-green-500', cyan: 'text-cyan-500', red: 'text-red-500',
  pink: 'text-pink-500', indigo: 'text-indigo-500', emerald: 'text-emerald-500',
};

const COLOR_BG = {
  purple: 'bg-purple-50', blue: 'bg-blue-50', amber: 'bg-amber-50',
  green: 'bg-green-50', cyan: 'bg-cyan-50', red: 'bg-red-50',
  pink: 'bg-pink-50', indigo: 'bg-indigo-50', emerald: 'bg-emerald-50',
};

const COLOR_HEX = {
  purple: '#a855f7', blue: '#3b82f6', amber: '#f59e0b',
  green: '#22c55e', cyan: '#06b6d4', red: '#ef4444',
  pink: '#ec4899', indigo: '#6366f1', emerald: '#10b981',
};

const STATUS_BADGE = {
  running: 'bg-emerald-100 text-emerald-700',
  idle: 'bg-gray-100 text-gray-600',
  error: 'bg-red-100 text-red-700',
};

const TASK_STATUS_DOT = {
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  pending: 'bg-gray-400',
  processing: 'bg-blue-500',
};

function formatRelativeTime(dateStr) {
  if (!dateStr) return '--';
  const age = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (age < 60) return `${Math.round(age)}s ago`;
  if (age < 3600) return `${Math.round(age / 60)}m ago`;
  if (age < 86400) return `${Math.round(age / 3600)}h ago`;
  return `${Math.round(age / 86400)}d ago`;
}

function SkeletonBlock({ className }) {
  return <div className={`bg-gray-200 rounded animate-pulse ${className}`} />;
}

/**
 * Slide-out detail panel for a single agent.
 * Fetches activity data on mount and displays metrics, cost sparkline, and recent tasks.
 * @param {{ agent: object, onClose: () => void }} props
 */
export default function AgentDetailPanel({ agent, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [soulOpen, setSoulOpen] = useState(false);

  const fetchActivity = () => {
    setLoading(true);
    setError(null);
    api.getAgentActivity(agent.name)
      .then((res) => setData(res.data))
      .catch((err) => setError(err.message || 'Failed to load agent activity'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchActivity(); }, [agent.name]);

  const Icon = ICON_MAP[agent.icon] || Sparkles;
  const fillColor = COLOR_HEX[agent.color] || '#6366f1';
  const metrics = data?.metrics_7d;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed right-0 top-0 bottom-0 w-[480px] bg-white border-l border-gray-200 z-50 overflow-y-auto animate-slide-in-right">
        <div className="p-6 space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg ${COLOR_BG[agent.color]} flex items-center justify-center`}>
                <Icon className={`w-5 h-5 ${COLOR_ICON[agent.color]}`} />
              </div>
              <div>
                <h2 className="font-semibold text-gray-900">{agent.display_name}</h2>
                <span className={`inline-block text-[11px] font-medium rounded-full px-2 py-0.5 mt-0.5 ${STATUS_BADGE[agent.status] || 'bg-gray-100 text-gray-600'}`}>
                  {agent.status}
                </span>
              </div>
            </div>
            <button type="button" onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Error state */}
          {error && (
            <div className="glass-card p-4 text-center">
              <p className="text-sm text-red-600 mb-2">{error}</p>
              <button type="button" onClick={fetchActivity} className="text-xs font-medium text-orange-600 hover:text-orange-700">
                Retry
              </button>
            </div>
          )}

          {/* Loading state */}
          {loading && !error && (
            <div className="space-y-4">
              <SkeletonBlock className="h-16 w-full" />
              <div className="grid grid-cols-2 gap-3">
                {[...Array(4)].map((_, i) => <SkeletonBlock key={i} className="h-16" />)}
              </div>
              <SkeletonBlock className="h-[120px] w-full" />
              <SkeletonBlock className="h-48 w-full" />
            </div>
          )}

          {/* Data loaded */}
          {data && !loading && (
            <>
              {/* Soul Summary (collapsible) */}
              {data.soul_summary && (
                <div className="glass-card">
                  <button type="button" onClick={() => setSoulOpen((prev) => !prev)} className="w-full flex items-center justify-between p-3 text-left">
                    <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Identity</span>
                    {soulOpen ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                  </button>
                  {soulOpen && (
                    <div className="px-3 pb-3">
                      <p className="text-sm text-gray-700 leading-relaxed">{data.soul_summary}</p>
                    </div>
                  )}
                </div>
              )}

              {/* 7-Day Metrics */}
              {metrics && (
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: 'Total Tasks', value: metrics.total_tasks },
                    { label: 'Success Rate', value: `${(metrics.success_rate * 100).toFixed(1)}%` },
                    { label: 'Avg Duration', value: `${metrics.avg_duration_s.toFixed(1)}s` },
                    { label: 'Total Cost', value: `$${metrics.total_cost.toFixed(3)}` },
                  ].map((stat) => (
                    <div key={stat.label} className="glass-card p-3">
                      <div className="text-[11px] text-gray-500 mb-1">{stat.label}</div>
                      <div className="text-lg font-semibold text-gray-900 font-mono">{stat.value}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Cost Sparkline */}
              {data.cost_history?.length > 0 && (
                <div className="glass-card p-3">
                  <div className="text-[11px] text-gray-500 mb-2 font-semibold uppercase tracking-wide">Cost (30d)</div>
                  <ResponsiveContainer width="100%" height={120}>
                    <AreaChart data={data.cost_history}>
                      <defs>
                        <linearGradient id={`fill-${agent.name}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={fillColor} stopOpacity={0.3} />
                          <stop offset="100%" stopColor={fillColor} stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="date" hide />
                      <Tooltip formatter={(v) => `$${Number(v).toFixed(4)}`} labelFormatter={(l) => l} />
                      <Area type="monotone" dataKey="cost" stroke={fillColor} fill={`url(#fill-${agent.name})`} strokeWidth={1.5} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Recent Tasks */}
              {data.recent_tasks?.length > 0 && (
                <div className="glass-card p-3">
                  <div className="text-[11px] text-gray-500 mb-2 font-semibold uppercase tracking-wide">Recent Tasks</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-gray-400 border-b border-gray-100">
                          <th className="text-left pb-1.5 font-medium">Type</th>
                          <th className="text-left pb-1.5 font-medium">Status</th>
                          <th className="text-right pb-1.5 font-medium">Duration</th>
                          <th className="text-right pb-1.5 font-medium">When</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.recent_tasks.slice(0, 10).map((task, idx) => (
                          <tr key={task.id ?? idx} className="border-b border-gray-50 last:border-0">
                            <td className="py-1.5 text-gray-700 font-medium">{task.task_type}</td>
                            <td className="py-1.5">
                              <span className="inline-flex items-center gap-1.5">
                                <span className={`w-1.5 h-1.5 rounded-full ${TASK_STATUS_DOT[task.status] || 'bg-gray-400'}`} />
                                <span className="text-gray-600">{task.status}</span>
                              </span>
                            </td>
                            <td className="py-1.5 text-right text-gray-500 font-mono">
                              {task.duration_s != null ? `${Number(task.duration_s).toFixed(1)}s` : '--'}
                            </td>
                            <td className="py-1.5 text-right text-gray-400">{formatRelativeTime(task.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
