import {
  FlaskConical, Thermometer, RefreshCw, Factory, Share2,
  Search, Gift, Brain, HeartPulse, Sparkles,
} from 'lucide-react';

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

const COLOR_BG = {
  purple: 'bg-purple-50', blue: 'bg-blue-50', amber: 'bg-amber-50',
  green: 'bg-green-50', cyan: 'bg-cyan-50', red: 'bg-red-50',
  pink: 'bg-pink-50', indigo: 'bg-indigo-50', emerald: 'bg-emerald-50',
};

const COLOR_ICON = {
  purple: 'text-purple-500', blue: 'text-blue-500', amber: 'text-amber-500',
  green: 'text-green-500', cyan: 'text-cyan-500', red: 'text-red-500',
  pink: 'text-pink-500', indigo: 'text-indigo-500', emerald: 'text-emerald-500',
};

const STATUS_DOT = {
  running: 'bg-emerald-500 animate-agent-pulse',
  idle: 'bg-gray-300',
  error: 'bg-red-500 animate-pulse',
};

/**
 * Formats seconds into a human-readable relative time string.
 */
function formatAge(heartbeat) {
  if (!heartbeat) return 'No data';
  const age = (Date.now() - new Date(heartbeat).getTime()) / 1000;
  if (age < 60) return `${Math.round(age)}s ago`;
  if (age < 3600) return `${Math.round(age / 60)}m ago`;
  if (age < 86400) return `${Math.round(age / 3600)}h ago`;
  return `${Math.round(age / 86400)}d ago`;
}

/**
 * Individual agent card with status pulse, cost, and task count.
 * @param {{ agent: object, selected: boolean, onClick: () => void }} props
 */
export default function AgentCard({ agent, selected, onClick }) {
  const Icon = ICON_MAP[agent.icon] || Sparkles;
  const dotClass = STATUS_DOT[agent.status] || 'bg-gray-300';

  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        glass-card p-5 text-left cursor-pointer card-hover-lift
        active:scale-[0.98] transition-all duration-150 w-full
        ${selected ? 'border-orange-400 ring-2 ring-orange-100' : ''}
      `}
    >
      {/* Header row: icon + status dot */}
      <div className="flex items-start justify-between mb-3">
        <div className={`w-9 h-9 rounded-lg ${COLOR_BG[agent.color]} flex items-center justify-center`}>
          <Icon className={`w-4.5 h-4.5 ${COLOR_ICON[agent.color]}`} />
        </div>
        <div className={`w-2.5 h-2.5 rounded-full ${dotClass}`} />
      </div>

      {/* Name + schedule */}
      <div className="font-semibold text-gray-900 text-sm leading-tight mb-0.5">
        {agent.display_name}
      </div>
      <div className="text-xs text-gray-500 mb-3">{agent.schedule}</div>

      {/* Bottom row: cost, tasks, heartbeat */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span className="font-mono">${agent.cost_today?.toFixed(3) ?? '0.000'}</span>
        <span>{agent.tasks_today ?? 0} tasks</span>
        <span>{formatAge(agent.last_heartbeat)}</span>
      </div>

      {/* Uses AI badge */}
      {agent.uses_ai && (
        <div className="mt-2.5">
          <span className="inline-flex items-center gap-1 text-[10px] font-medium text-purple-600 bg-purple-50 rounded-full px-2 py-0.5">
            <Sparkles className="w-2.5 h-2.5" /> AI
          </span>
        </div>
      )}
    </button>
  );
}
