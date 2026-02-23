import { useState, useMemo } from 'react';
import {
  Send, GitBranch, Database, Search, Settings, Activity,
  HeartPulse, RotateCw, Shield, FlaskConical, Brain,
  RefreshCw, Gift, Mail,
} from 'lucide-react';
import useSystemMap from '../../hooks/useSystemMap';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ICON_MAP = {
  send: Send, 'git-branch': GitBranch, database: Database,
  search: Search, cog: Settings, activity: Activity,
  'heart-pulse': HeartPulse, 'rotate-cw': RotateCw, shield: Shield,
  'flask-conical': FlaskConical, brain: Brain, 'refresh-cw': RefreshCw,
  gift: Gift, mail: Mail,
};

const COLOR_FILL = {
  sky: '#0ea5e9', lime: '#84cc16', orange: '#f97316', cyan: '#06b6d4',
  gray: '#6b7280', green: '#22c55e', emerald: '#10b981', stone: '#78716c',
  violet: '#8b5cf6', red: '#ef4444', purple: '#a855f7', amber: '#f59e0b',
  indigo: '#6366f1', pink: '#ec4899',
};

const COLOR_BG_LIGHT = {
  sky: '#f0f9ff', lime: '#f7fee7', orange: '#fff7ed', cyan: '#ecfeff',
  gray: '#f9fafb', green: '#f0fdf4', emerald: '#ecfdf5', stone: '#fafaf9',
  violet: '#f5f3ff', red: '#fef2f2', purple: '#faf5ff', amber: '#fffbeb',
  indigo: '#eef2ff', pink: '#fdf2f8',
};

// Stage definitions
const STAGES = [
  {
    id: 'inbound',
    label: 'Inbound',
    description: 'Leads arrive',
    items: [
      { type: 'metric', key: 'new', label: 'New Leads' },
    ],
  },
  {
    id: 'processing',
    label: 'Processing',
    description: 'AI agent pipeline',
    agents: ['lead_state_manager', 'task_processor'],
    items: [
      { type: 'metric', key: 'intake_sent', label: 'Intake Sent' },
      { type: 'metric', key: 'qualifying', label: 'Qualifying' },
      { type: 'metric', key: 'qualified', label: 'Qualified' },
      { type: 'metric', key: 'booking', label: 'Booking' },
    ],
  },
  {
    id: 'outbound',
    label: 'Outbound',
    description: 'Communication',
    agents: ['sms_dispatch', 'crm_sync', 'outreach_sequencer'],
    items: [
      { type: 'today', key: 'sms_sent_today', label: 'SMS Today' },
      { type: 'today', key: 'emails_sent_today', label: 'Emails Today' },
    ],
  },
  {
    id: 'outcomes',
    label: 'Outcomes',
    description: 'Results',
    items: [
      { type: 'metric', key: 'booked', label: 'Booked' },
      { type: 'metric', key: 'completed', label: 'Completed' },
      { type: 'metric', key: 'cold', label: 'Cold' },
      { type: 'metric', key: 'opted_out', label: 'Opted Out' },
      { type: 'today', key: 'bookings_today', label: 'Bookings Today' },
    ],
  },
];

const SUPPORT_AGENTS = [
  'system_health', 'retry_worker', 'outreach_monitor', 'registration_poller',
];

const INTELLIGENCE_AGENTS = [
  'ab_test_engine', 'reflection_agent', 'winback_agent', 'referral_agent', 'scraper',
];

const AGENT_META = {
  sms_dispatch: { display_name: 'SMS Dispatch', icon: 'send', color: 'sky' },
  lead_state_manager: { display_name: 'Lead State', icon: 'git-branch', color: 'lime' },
  crm_sync: { display_name: 'CRM Sync', icon: 'database', color: 'orange' },
  outreach_sequencer: { display_name: 'Outreach Seq', icon: 'mail', color: 'red' },
  ab_test_engine: { display_name: 'A/B Testing', icon: 'flask-conical', color: 'purple' },
  winback_agent: { display_name: 'Win-Back', icon: 'refresh-cw', color: 'amber' },
  reflection_agent: { display_name: 'Reflection', icon: 'brain', color: 'indigo' },
  system_health: { display_name: 'Sys Health', icon: 'activity', color: 'green' },
  scraper: { display_name: 'Scraper', icon: 'search', color: 'cyan' },
  task_processor: { display_name: 'Task Proc', icon: 'cog', color: 'gray' },
  outreach_monitor: { display_name: 'Monitor', icon: 'heart-pulse', color: 'emerald' },
  retry_worker: { display_name: 'Retry Queue', icon: 'rotate-cw', color: 'stone' },
  registration_poller: { display_name: 'A2P Reg', icon: 'shield', color: 'violet' },
  referral_agent: { display_name: 'Referral', icon: 'gift', color: 'pink' },
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CountBadge({ value }) {
  return (
    <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[11px] font-semibold bg-gray-100 text-gray-700 rounded-full font-mono">
      {value ?? 0}
    </span>
  );
}

function AgentChip({ name, onClick }) {
  const meta = AGENT_META[name] || {};
  const Icon = ICON_MAP[meta.icon] || Activity;
  const fill = COLOR_FILL[meta.color] || '#6b7280';

  return (
    <button
      type="button"
      onClick={() => onClick?.(name)}
      className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium bg-white border border-gray-200 hover:border-gray-300 hover:shadow-sm transition-all cursor-pointer group"
    >
      <Icon className="w-3.5 h-3.5 shrink-0" style={{ color: fill }} />
      <span className="text-gray-700 group-hover:text-gray-900">{meta.display_name || name}</span>
    </button>
  );
}

function StageCard({ stage, mapData, onAgentClick }) {
  const leadCounts = mapData?.lead_counts || {};

  return (
    <div className="glass-card p-4 flex-1 min-w-[180px]">
      <div className="mb-3">
        <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">{stage.label}</h4>
        <p className="text-[11px] text-gray-400">{stage.description}</p>
      </div>

      {/* Metrics */}
      <div className="space-y-1.5 mb-3">
        {stage.items.map((item) => {
          const value = item.type === 'metric'
            ? (leadCounts[item.key] ?? 0)
            : (mapData?.[item.key] ?? 0);
          return (
            <div key={item.key} className="flex items-center justify-between">
              <span className="text-xs text-gray-600">{item.label}</span>
              <CountBadge value={value} />
            </div>
          );
        })}
      </div>

      {/* Agent chips */}
      {stage.agents && stage.agents.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-2 border-t border-gray-100">
          {stage.agents.map((a) => (
            <AgentChip key={a} name={a} onClick={onAgentClick} />
          ))}
        </div>
      )}
    </div>
  );
}

function AgentGroup({ title, description, agents, onAgentClick }) {
  return (
    <div className="glass-card p-4">
      <div className="mb-2">
        <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">{title}</h4>
        <p className="text-[11px] text-gray-400">{description}</p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {agents.map((a) => (
          <AgentChip key={a} name={a} onClick={onAgentClick} />
        ))}
      </div>
    </div>
  );
}

// Flow arrow between stages (pure CSS)
function FlowArrow() {
  return (
    <div className="hidden lg:flex items-center px-1">
      <div className="w-8 h-px bg-gradient-to-r from-gray-300 to-gray-200 relative">
        <div className="absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0 border-t-[4px] border-b-[4px] border-l-[6px] border-transparent border-l-gray-300" />
        {/* Animated dash overlay */}
        <div
          className="absolute inset-0 h-px"
          style={{
            background: 'repeating-linear-gradient(90deg, #d1d5db 0, #d1d5db 4px, transparent 4px, transparent 8px)',
            animation: 'flowDash 1.5s linear infinite',
          }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Interactive system map showing lead flow, agent positions, and live counts.
 * @param {{ onSelectAgent?: (name: string) => void }} props
 */
export default function SystemMap({ onSelectAgent }) {
  const { data: mapData, loading, error } = useSystemMap();

  const handleAgentClick = (name) => {
    onSelectAgent?.(name);
  };

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="flex gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-48 flex-1 bg-gray-100 rounded-xl" />
          ))}
        </div>
        <div className="flex gap-4">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-24 flex-1 bg-gray-100 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card p-6 text-center">
        <p className="text-sm text-red-600 mb-2">{error}</p>
      </div>
    );
  }

  // Compute totals for the summary row
  const leadCounts = mapData?.lead_counts || {};
  const totalActive = Object.entries(leadCounts)
    .filter(([s]) => !['dead', 'opted_out', 'completed'].includes(s))
    .reduce((sum, [, v]) => sum + v, 0);

  return (
    <div className="animate-fade-up space-y-4">
      {/* Summary banner */}
      <div className="flex items-center gap-6 px-4 py-2.5 bg-gradient-to-r from-orange-50 to-amber-50 rounded-xl border border-orange-100">
        <div className="text-xs text-gray-500">
          <span className="font-semibold text-gray-900 text-lg font-mono mr-1">{totalActive}</span>
          active leads
        </div>
        <div className="text-xs text-gray-500">
          <span className="font-semibold text-gray-900 text-lg font-mono mr-1">{mapData?.sms_sent_today ?? 0}</span>
          SMS today
        </div>
        <div className="text-xs text-gray-500">
          <span className="font-semibold text-gray-900 text-lg font-mono mr-1">{mapData?.bookings_today ?? 0}</span>
          bookings today
        </div>
        <div className="text-xs text-gray-500">
          <span className="font-semibold text-gray-900 text-lg font-mono mr-1">{mapData?.emails_sent_today ?? 0}</span>
          emails today
        </div>
      </div>

      {/* Main flow: 4 stages left-to-right */}
      <div className="flex flex-col lg:flex-row items-stretch gap-2">
        {STAGES.map((stage, idx) => (
          <div key={stage.id} className="flex items-stretch flex-1 min-w-0">
            {idx > 0 && <FlowArrow />}
            <StageCard stage={stage} mapData={mapData} onAgentClick={handleAgentClick} />
          </div>
        ))}
      </div>

      {/* Bottom row: Support + Intelligence */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AgentGroup
          title="Support"
          description="Monitoring, retry, infrastructure"
          agents={SUPPORT_AGENTS}
          onAgentClick={handleAgentClick}
        />
        <AgentGroup
          title="Intelligence"
          description="Optimization, learning, outreach"
          agents={INTELLIGENCE_AGENTS}
          onAgentClick={handleAgentClick}
        />
      </div>

      {/* CSS animation keyframes */}
      <style>{`
        @keyframes flowDash {
          0% { transform: translateX(0); }
          100% { transform: translateX(8px); }
        }
      `}</style>
    </div>
  );
}
