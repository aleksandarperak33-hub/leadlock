import { useState } from 'react';
import {
  Send, Search, Settings, Activity,
  HeartPulse, RotateCw, Shield, FlaskConical, Brain,
  RefreshCw, Gift, Mail, Users, Target, BarChart3,
  TrendingUp, Zap, MessageSquare,
} from 'lucide-react';
import useSystemMap from '../../hooks/useSystemMap';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ICON_MAP = {
  send: Send, search: Search, cog: Settings, activity: Activity,
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

const AGENT_META = {
  scraper: { display_name: 'Prospect Scraper', icon: 'search', color: 'cyan' },
  outreach_sequencer: { display_name: 'Outreach Sequencer', icon: 'mail', color: 'red' },
  ab_test_engine: { display_name: 'A/B Testing', icon: 'flask-conical', color: 'purple' },
  winback_agent: { display_name: 'Win-Back Agent', icon: 'refresh-cw', color: 'amber' },
  reflection_agent: { display_name: 'Reflection Agent', icon: 'brain', color: 'indigo' },
  outreach_monitor: { display_name: 'Outreach Monitor', icon: 'heart-pulse', color: 'emerald' },
  referral_agent: { display_name: 'Referral Agent', icon: 'gift', color: 'pink' },
};

// Pipeline stages for the sales distribution flow
const PIPELINE_STAGES = [
  {
    id: 'discovery',
    label: 'Discovery',
    icon: Search,
    color: 'cyan',
    description: 'Find prospects',
    agents: ['scraper'],
    metrics: [
      { key: 'cold', label: 'New / Cold', source: 'prospect' },
    ],
  },
  {
    id: 'outreach',
    label: 'Outreach',
    icon: Mail,
    color: 'red',
    description: 'Email sequences',
    agents: ['outreach_sequencer', 'ab_test_engine'],
    metrics: [
      { key: 'contacted', label: 'In Sequence', source: 'prospect' },
      { key: 'emails_sent_today', label: 'Emails Today', source: 'top' },
    ],
  },
  {
    id: 'engagement',
    label: 'Engagement',
    icon: MessageSquare,
    color: 'purple',
    description: 'Replies & demos',
    agents: ['winback_agent', 'referral_agent'],
    metrics: [
      { key: 'demo_scheduled', label: 'Demos Scheduled', source: 'prospect' },
      { key: 'demo_completed', label: 'Demos Done', source: 'prospect' },
      { key: 'emails_replied_today', label: 'Replies Today', source: 'top' },
    ],
  },
  {
    id: 'conversion',
    label: 'Conversion',
    icon: TrendingUp,
    color: 'green',
    description: 'Close deals',
    agents: [],
    metrics: [
      { key: 'proposal_sent', label: 'Proposals Sent', source: 'prospect' },
      { key: 'won', label: 'Won', source: 'prospect' },
      { key: 'lost', label: 'Lost', source: 'prospect' },
    ],
  },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CountBadge({ value, highlight }) {
  const base = highlight
    ? 'bg-green-100 text-green-800'
    : 'bg-gray-100 text-gray-700';
  return (
    <span className={`inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[11px] font-semibold rounded-full font-mono ${base}`}>
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

function FlowArrow() {
  return (
    <div className="hidden lg:flex items-center px-1 shrink-0">
      <div className="w-8 h-px bg-gradient-to-r from-gray-300 to-gray-200 relative">
        <div className="absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0 border-t-[4px] border-b-[4px] border-l-[6px] border-transparent border-l-gray-300" />
      </div>
    </div>
  );
}

function StageCard({ stage, mapData, onAgentClick }) {
  const prospects = mapData?.prospect_counts || {};
  const StageIcon = stage.icon;

  return (
    <div className="glass-card p-4 flex-1 min-w-[170px]">
      <div className="flex items-center gap-2 mb-3">
        <div className={`w-7 h-7 rounded-lg bg-${stage.color}-50 flex items-center justify-center`}>
          <StageIcon className="w-4 h-4" style={{ color: COLOR_FILL[stage.color] }} />
        </div>
        <div>
          <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">{stage.label}</h4>
          <p className="text-[10px] text-gray-400">{stage.description}</p>
        </div>
      </div>

      {/* Metrics */}
      <div className="space-y-1.5 mb-3">
        {stage.metrics.map((m) => {
          const value = m.source === 'prospect'
            ? (prospects[m.key] ?? 0)
            : (mapData?.[m.key] ?? 0);
          const highlight = m.key === 'won';
          return (
            <div key={m.key} className="flex items-center justify-between">
              <span className="text-xs text-gray-600">{m.label}</span>
              <CountBadge value={value} highlight={highlight} />
            </div>
          );
        })}
      </div>

      {/* Agent chips */}
      {stage.agents.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-2 border-t border-gray-100">
          {stage.agents.map((a) => (
            <AgentChip key={a} name={a} onClick={onAgentClick} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Interactive system map for the sales distribution pipeline.
 * Shows how LeadLock finds and converts B2B prospects into customers.
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
        <div className="h-16 bg-gray-100 rounded-xl" />
        <div className="flex gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={`skel-${i}`} className="h-52 flex-1 bg-gray-100 rounded-xl" />
          ))}
        </div>
        <div className="h-20 bg-gray-100 rounded-xl" />
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

  const prospects = mapData?.prospect_counts || {};
  const campaigns = mapData?.campaign_counts || {};
  const totalProspects = mapData?.total_prospects ?? 0;
  const activeCampaigns = campaigns.active ?? 0;
  const wonCount = prospects.won ?? 0;
  const lostCount = prospects.lost ?? 0;
  const conversionRate = (wonCount + lostCount) > 0
    ? ((wonCount / (wonCount + lostCount)) * 100).toFixed(1)
    : '0.0';

  return (
    <div className="animate-fade-up space-y-4">
      {/* Summary banner */}
      <div className="flex flex-wrap items-center gap-6 px-4 py-3 bg-gradient-to-r from-orange-50 to-amber-50 rounded-xl border border-orange-100">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-gray-400" />
          <div className="text-xs text-gray-500">
            <span className="font-semibold text-gray-900 text-lg font-mono mr-1">{totalProspects}</span>
            prospects
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-gray-400" />
          <div className="text-xs text-gray-500">
            <span className="font-semibold text-gray-900 text-lg font-mono mr-1">{activeCampaigns}</span>
            active campaigns
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Mail className="w-4 h-4 text-gray-400" />
          <div className="text-xs text-gray-500">
            <span className="font-semibold text-gray-900 text-lg font-mono mr-1">{mapData?.emails_sent_today ?? 0}</span>
            emails today
          </div>
        </div>
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-gray-400" />
          <div className="text-xs text-gray-500">
            <span className="font-semibold text-gray-900 text-lg font-mono mr-1">{mapData?.emails_opened_today ?? 0}</span>
            opened today
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-gray-400" />
          <div className="text-xs text-gray-500">
            <span className="font-semibold text-green-700 text-lg font-mono mr-1">{wonCount}</span>
            won
            <span className="text-gray-400 ml-1">({conversionRate}%)</span>
          </div>
        </div>
      </div>

      {/* Pipeline flow: 4 stages left-to-right */}
      <div className="flex flex-col lg:flex-row items-stretch gap-2">
        {PIPELINE_STAGES.map((stage, idx) => (
          <div key={stage.id} className="flex items-stretch flex-1 min-w-0">
            {idx > 0 && <FlowArrow />}
            <StageCard stage={stage} mapData={mapData} onAgentClick={handleAgentClick} />
          </div>
        ))}
      </div>

      {/* Support row: Monitor + Reflection */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <HeartPulse className="w-4 h-4 text-emerald-500" />
            <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">Pipeline Health</h4>
          </div>
          <p className="text-[11px] text-gray-400 mb-3">Anomaly detection, sequence cleanup, deliverability</p>
          <div className="flex flex-wrap gap-1.5">
            <AgentChip name="outreach_monitor" onClick={handleAgentClick} />
          </div>
        </div>
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-4 h-4 text-indigo-500" />
            <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">Intelligence</h4>
          </div>
          <p className="text-[11px] text-gray-400 mb-3">
            Daily audit, A/B optimization
            {mapData?.ab_tests_today > 0 && (
              <span className="ml-2 text-purple-600 font-medium">{mapData.ab_tests_today} tests today</span>
            )}
          </p>
          <div className="flex flex-wrap gap-1.5">
            <AgentChip name="reflection_agent" onClick={handleAgentClick} />
          </div>
        </div>
      </div>
    </div>
  );
}
