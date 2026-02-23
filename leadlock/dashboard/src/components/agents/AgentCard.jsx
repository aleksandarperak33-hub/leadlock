import {
  FlaskConical, Thermometer, RefreshCw, Factory, Share2,
  Search, Gift, Brain, HeartPulse, Sparkles,
  Mail, Settings, Trash2, ShieldCheck, Activity,
  Database, Send, Bell, GitBranch, AlertTriangle,
  RotateCw, Shield,
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
  'mail': Mail,
  'cog': Settings,
  'trash-2': Trash2,
  'shield-check': ShieldCheck,
  'activity': Activity,
  'database': Database,
  'send': Send,
  'bell': Bell,
  'git-branch': GitBranch,
  'alert-triangle': AlertTriangle,
  'rotate-cw': RotateCw,
  'shield': Shield,
};

const COLOR_BG = {
  purple: 'bg-purple-50', blue: 'bg-blue-50', amber: 'bg-amber-50',
  green: 'bg-green-50', cyan: 'bg-cyan-50', red: 'bg-red-50',
  pink: 'bg-pink-50', indigo: 'bg-indigo-50', emerald: 'bg-emerald-50',
  teal: 'bg-teal-50', sky: 'bg-sky-50', lime: 'bg-lime-50',
  rose: 'bg-rose-50', slate: 'bg-slate-50', stone: 'bg-stone-50',
  violet: 'bg-violet-50', orange: 'bg-orange-50', yellow: 'bg-yellow-50',
  gray: 'bg-gray-50',
};

const COLOR_ICON = {
  purple: 'text-purple-500', blue: 'text-blue-500', amber: 'text-amber-500',
  green: 'text-green-500', cyan: 'text-cyan-500', red: 'text-red-500',
  pink: 'text-pink-500', indigo: 'text-indigo-500', emerald: 'text-emerald-500',
  teal: 'text-teal-500', sky: 'text-sky-500', lime: 'text-lime-500',
  rose: 'text-rose-500', slate: 'text-slate-500', stone: 'text-stone-500',
  violet: 'text-violet-500', orange: 'text-orange-500', yellow: 'text-yellow-500',
  gray: 'text-gray-500',
};

const COLOR_BORDER = {
  purple: 'border-purple-300', blue: 'border-blue-300', amber: 'border-amber-300',
  green: 'border-green-300', cyan: 'border-cyan-300', red: 'border-red-300',
  pink: 'border-pink-300', indigo: 'border-indigo-300', emerald: 'border-emerald-300',
  teal: 'border-teal-300', sky: 'border-sky-300', lime: 'border-lime-300',
  rose: 'border-rose-300', slate: 'border-slate-300', stone: 'border-stone-300',
  violet: 'border-violet-300', orange: 'border-orange-300', yellow: 'border-yellow-300',
  gray: 'border-gray-300',
};

const STATUS_DOT = {
  running: 'bg-emerald-500 animate-agent-pulse',
  idle: 'bg-gray-300',
  error: 'bg-red-500 animate-pulse',
  disabled: 'bg-gray-300',
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
 * AI tier agents get a larger card with accent border.
 * @param {{ agent: object, tier: string, selected: boolean, onClick: () => void }} props
 */
export default function AgentCard({ agent, tier, selected, onClick }) {
  const Icon = ICON_MAP[agent.icon] || Sparkles;
  const dotClass = STATUS_DOT[agent.status] || 'bg-gray-300';
  const isDisabled = agent.enabled === false;
  const isAI = tier === 'ai';

  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        glass-card p-5 text-left cursor-pointer card-hover-lift
        active:scale-[0.98] transition-all duration-150 w-full
        ${selected ? 'border-orange-400 ring-2 ring-orange-100' : ''}
        ${isDisabled ? 'opacity-50' : ''}
        ${isAI ? `border-l-4 ${COLOR_BORDER[agent.color]}` : ''}
      `}
    >
      {/* Header row: icon + status dot */}
      <div className="flex items-start justify-between mb-3">
        <div className={`${isAI ? 'w-10 h-10' : 'w-9 h-9'} rounded-lg ${COLOR_BG[agent.color]} flex items-center justify-center`}>
          <Icon className={`${isAI ? 'w-5 h-5' : 'w-4.5 h-4.5'} ${COLOR_ICON[agent.color]}`} />
        </div>
        <div className="flex items-center gap-1.5">
          {isDisabled && (
            <span className="text-[10px] font-medium text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">
              OFF
            </span>
          )}
          <div className={`w-2.5 h-2.5 rounded-full ${dotClass}`} />
        </div>
      </div>

      {/* Name + schedule */}
      <div className={`font-semibold text-gray-900 leading-tight mb-0.5 ${isAI ? 'text-sm' : 'text-sm'}`}>
        {agent.display_name}
      </div>
      <div className="text-xs text-gray-500 mb-3">{agent.schedule}</div>

      {/* Bottom row: cost, tasks, heartbeat */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span className="font-mono">${agent.cost_today?.toFixed(3) ?? '0.000'}</span>
        <span>{agent.tasks_today ?? 0} tasks</span>
        <span>{isDisabled ? 'Disabled' : formatAge(agent.last_heartbeat)}</span>
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
