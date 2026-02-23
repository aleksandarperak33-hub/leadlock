import { useState, lazy, Suspense } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import Tabs from '../../components/ui/Tabs';
import FleetSummaryBar from '../../components/agents/FleetSummaryBar';
import AgentCard from '../../components/agents/AgentCard';
import AgentCardSkeleton from '../../components/agents/AgentCardSkeleton';
import AgentDetailPanel from '../../components/agents/AgentDetailPanel';
import useAgentFleet from '../../hooks/useAgentFleet';

// Lazy-load heavier tab components
const SystemMap = lazy(() => import('../../components/agents/SystemMap'));
const TaskQueueMonitor = lazy(() => import('../../components/agents/TaskQueueMonitor'));
const CostDashboard = lazy(() => import('../../components/agents/CostDashboard'));
const ActivityTimeline = lazy(() => import('../../components/agents/ActivityTimeline'));

const TABS = [
  { id: 'map', label: 'System Map' },
  { id: 'fleet', label: 'Fleet' },
  { id: 'tasks', label: 'Task Queue' },
  { id: 'costs', label: 'Costs' },
  { id: 'activity', label: 'Activity' },
];

const TIER_ORDER = ['ai', 'core_ops', 'infra'];
const TIER_LABELS = {
  ai: 'AI Agents',
  core_ops: 'Core Operations',
  infra: 'Infrastructure',
};
const TIER_DESCRIPTIONS = {
  ai: 'Use Claude API, generate revenue',
  core_ops: 'Lead-touching, business logic',
  infra: 'Monitoring, maintenance',
};

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <div className="w-6 h-6 border-2 border-orange-200 border-t-orange-500 rounded-full animate-spin" />
    </div>
  );
}

/**
 * Formats ISO timestamp to "10:17 AM" style.
 */
function formatTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

/**
 * Groups agents by their tier field.
 */
function groupByTier(agents) {
  const grouped = {};
  for (const tier of TIER_ORDER) {
    grouped[tier] = [];
  }
  for (const agent of agents) {
    const tier = agent.tier || 'infra';
    if (!grouped[tier]) grouped[tier] = [];
    grouped[tier].push(agent);
  }
  return grouped;
}

/**
 * Agent Army — mission control for the 14-agent fleet.
 * 5 tabs: System Map (default), Fleet, Task Queue, Costs, Activity.
 * Fleet tab renders agents in 3 tiers: AI Agents, Core Operations, Infrastructure.
 */
export default function AdminAgents() {
  const { data, loading, error, refresh } = useAgentFleet();
  const [activeTab, setActiveTab] = useState('map');
  const [selectedAgent, setSelectedAgent] = useState(null);

  const agents = data?.agents ?? [];
  const summary = data?.fleet_summary;
  const liveCount = summary ? `${summary.total_agents} agents` : '';
  const updatedAt = summary?.updated_at ? `Updated ${formatTime(summary.updated_at)}` : '';

  const tierGroups = groupByTier(agents);

  return (
    <div className="animate-page-in">
      <PageHeader
        title="Agent Army"
        subtitle={`${liveCount}${updatedAt ? ` \u00B7 ${updatedAt}` : ''}`}
        actions={
          <button
            onClick={refresh}
            className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        }
      />

      {/* Error banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-xl flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
          <button onClick={refresh} className="ml-auto text-red-600 hover:underline text-xs font-medium">
            Retry
          </button>
        </div>
      )}

      {/* Fleet summary bar */}
      <div className="mb-5">
        <FleetSummaryBar summary={summary} />
      </div>

      {/* Tabs */}
      <div className="mb-5">
        <Tabs tabs={TABS} activeId={activeTab} onChange={setActiveTab} />
      </div>

      {/* Tab content */}
      {activeTab === 'map' && (
        <Suspense fallback={<TabLoader />}>
          <SystemMap
            onSelectAgent={(name) => {
              const agent = agents.find((a) => a.name === name);
              if (agent) setSelectedAgent(agent);
            }}
          />
        </Suspense>
      )}

      {activeTab === 'fleet' && (
        <div className="animate-fade-up">
          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 14 }).map((_, i) => (
                <AgentCardSkeleton key={i} />
              ))}
            </div>
          ) : (
            <div className="space-y-8 stagger-in">
              {TIER_ORDER.map((tier) => {
                const tierAgents = tierGroups[tier] || [];
                if (tierAgents.length === 0) return null;
                return (
                  <div key={tier}>
                    {/* Tier header */}
                    <div className="mb-3">
                      <h3 className="text-sm font-semibold text-gray-900">{TIER_LABELS[tier]}</h3>
                      <p className="text-xs text-gray-500">{TIER_DESCRIPTIONS[tier]}</p>
                    </div>
                    {/* Agent cards */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {tierAgents.map((agent) => (
                        <AgentCard
                          key={agent.name}
                          agent={agent}
                          tier={tier}
                          selected={selectedAgent?.name === agent.name}
                          onClick={() => setSelectedAgent(
                            selectedAgent?.name === agent.name ? null : agent
                          )}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === 'tasks' && (
        <Suspense fallback={<TabLoader />}>
          <TaskQueueMonitor />
        </Suspense>
      )}

      {activeTab === 'costs' && (
        <Suspense fallback={<TabLoader />}>
          <CostDashboard />
        </Suspense>
      )}

      {activeTab === 'activity' && (
        <Suspense fallback={<TabLoader />}>
          <ActivityTimeline />
        </Suspense>
      )}

      {/* Detail panel (slides in from right) */}
      {selectedAgent && (
        <AgentDetailPanel
          agent={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
}
