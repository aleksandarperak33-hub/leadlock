import { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, DollarSign, Zap, AlertCircle, FlaskConical } from 'lucide-react';
import { api } from '../../api/client';
import PageHeader from '../../components/ui/PageHeader';
import FunnelChart from '../../components/FunnelChart';

function SectionCard({ title, icon: Icon, children }) {
  return (
    <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card mb-6">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="w-8 h-8 rounded-lg bg-orange-50 flex items-center justify-center">
          <Icon className="w-4 h-4 text-orange-500" />
        </div>
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function BarRow({ label, value, numericValue, maxValue, suffix = '' }) {
  const num = typeof numericValue === 'number' ? numericValue : Number(numericValue || 0);
  const pct = maxValue > 0 ? Math.round((num / maxValue) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-700 w-40 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-3 rounded-full overflow-hidden bg-orange-100">
        <div
          className="h-full bg-orange-500 rounded-full transition-all duration-500"
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      <span className="text-sm font-mono text-gray-900 w-20 text-right">
        {value}{suffix}
      </span>
    </div>
  );
}

function AbTestTable({ tests }) {
  if (!tests || tests.length === 0) {
    return <p className="text-sm text-gray-400">No A/B tests running.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            <th className="text-left text-xs font-medium text-gray-500 pb-2">Test</th>
            <th className="text-right text-xs font-medium text-gray-500 pb-2">Variant A</th>
            <th className="text-right text-xs font-medium text-gray-500 pb-2">Variant B</th>
            <th className="text-right text-xs font-medium text-gray-500 pb-2">Winner</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {tests.map((t, i) => (
            <tr key={t.id || i}>
              <td className="py-2 text-gray-700 max-w-[180px] truncate">{t.name || t.subject || `Test ${i + 1}`}</td>
              <td className="py-2 text-right font-mono text-gray-600">
                {t.variant_a_rate != null ? `${(t.variant_a_rate * 100).toFixed(1)}%` : '—'}
              </td>
              <td className="py-2 text-right font-mono text-gray-600">
                {t.variant_b_rate != null ? `${(t.variant_b_rate * 100).toFixed(1)}%` : '—'}
              </td>
              <td className="py-2 text-right">
                {t.winner ? (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700">
                    {t.winner}
                  </span>
                ) : (
                  <span className="text-xs text-gray-400">Running</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CostPerLeadSection({ data }) {
  if (!data) return <p className="text-sm text-gray-400">No data available.</p>;
  const items = Array.isArray(data) ? data : Object.entries(data).map(([trade, cost]) => ({ trade, cost: Number(cost) || 0 }));
  if (items.length === 0) return <p className="text-sm text-gray-400">No data available.</p>;
  const maxCost = Math.max(...items.map((i) => Number(i.cost || 0)), 0.01);
  return (
    <div className="space-y-3">
      {items.map((item, i) => {
        const cost = Number(item.cost || 0);
        return (
          <BarRow
            key={item.trade || i}
            label={item.trade || 'Overall'}
            value={`$${cost.toFixed(2)}`}
            numericValue={cost}
            maxValue={maxCost}
          />
        );
      })}
    </div>
  );
}

/** Extract .data from API response envelope {"success": true, "data": ...} */
function unwrap(response) {
  if (response && typeof response === 'object' && 'data' in response) {
    return response.data;
  }
  return response;
}

export default function AdminAnalytics() {
  const [pipeline, setPipeline] = useState(null);
  const [emailPerf, setEmailPerf] = useState(null);
  const [abTests, setAbTests] = useState(null);
  const [agentCosts, setAgentCosts] = useState(null);
  const [costPerLead, setCostPerLead] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, ep, ab, ac, cpl] = await Promise.allSettled([
        api.getAnalyticsPipeline(),
        api.getAnalyticsEmailPerf(),
        api.getAnalyticsAbTests(),
        api.getAnalyticsAgentCosts(),
        api.getAnalyticsCostPerLead(),
      ]);
      if (p.status === 'fulfilled') setPipeline(unwrap(p.value));
      if (ep.status === 'fulfilled') setEmailPerf(unwrap(ep.value));
      if (ab.status === 'fulfilled') setAbTests(unwrap(ab.value));
      if (ac.status === 'fulfilled') setAgentCosts(unwrap(ac.value));
      if (cpl.status === 'fulfilled') setCostPerLead(unwrap(cpl.value));
      const allFailed = [p, ep, ab, ac, cpl].every((r) => r.status === 'rejected');
      if (allFailed) throw new Error('All analytics endpoints failed.');
    } catch (err) {
      setError(err.message || 'Failed to load analytics.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Email performance: backend returns {steps: [{step, total_sent, open_rate, ...}]}
  const emailPerfItems = emailPerf?.steps || [];
  const maxEmailOpen = Math.max(...emailPerfItems.map((e) => Number(e.open_rate || 0)), 0.01);

  // Agent costs: backend returns {total_by_agent: {agent_name: cost}, total_usd, ...}
  const agentCostItems = agentCosts?.total_by_agent
    ? Object.entries(agentCosts.total_by_agent).map(([agent, cost]) => ({ agent, cost: Number(cost) || 0 }))
    : [];
  const maxAgentCost = Math.max(...agentCostItems.map((a) => a.cost), 0.01);

  // A/B tests: backend returns array or {experiments: [...]}
  const abTestItems = Array.isArray(abTests)
    ? abTests
    : abTests?.experiments || (abTests ? [abTests] : []);

  // Pipeline: backend returns {stages: {status: count}}
  const pipelineStages = pipeline?.stages || pipeline;

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <PageHeader title="Analytics" subtitle="Pipeline, email performance, A/B tests, and costs" />

      {error && (
        <div className="mb-4 flex items-center gap-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
          <p className="text-sm text-red-700 flex-1">{error}</p>
          <button onClick={loadAll} className="text-xs font-medium text-red-600 hover:text-red-800 cursor-pointer">
            Retry
          </button>
        </div>
      )}

      {pipelineStages && (
        <SectionCard title="Pipeline Waterfall" icon={TrendingUp}>
          <FunnelChart stages={pipelineStages} />
        </SectionCard>
      )}

      {emailPerfItems.length > 0 && (
        <SectionCard title="Email Performance by Step" icon={BarChart3}>
          <div className="space-y-3">
            {emailPerfItems.map((item, i) => {
              const openRate = Number(item.open_rate || 0);
              return (
                <BarRow
                  key={item.step ?? i}
                  label={`Step ${item.step ?? i + 1}`}
                  value={`${(openRate * 100).toFixed(1)}%`}
                  numericValue={openRate}
                  maxValue={maxEmailOpen}
                />
              );
            })}
          </div>
        </SectionCard>
      )}

      <SectionCard title="A/B Test Results" icon={FlaskConical}>
        <AbTestTable tests={abTestItems} />
      </SectionCard>

      {agentCostItems.length > 0 && (
        <SectionCard title="Agent Costs (Last 7 Days)" icon={Zap}>
          <div className="space-y-3">
            {agentCostItems.map((item, i) => (
              <BarRow
                key={item.agent || i}
                label={item.agent || `Agent ${i + 1}`}
                value={`$${item.cost.toFixed(4)}`}
                numericValue={item.cost}
                maxValue={maxAgentCost}
              />
            ))}
          </div>
        </SectionCard>
      )}

      {agentCosts && (
        <div className="mb-6 text-right text-sm text-gray-500 font-mono">
          Total AI spend (7d): ${Number(agentCosts.total_usd || 0).toFixed(4)}
        </div>
      )}

      <SectionCard title="Cost Per Lead by Trade" icon={DollarSign}>
        <CostPerLeadSection data={costPerLead} />
      </SectionCard>
    </div>
  );
}
