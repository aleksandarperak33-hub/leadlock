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

function BarRow({ label, value, maxValue, suffix = '' }) {
  const pct = maxValue > 0 ? Math.round((value / maxValue) * 100) : 0;
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
  const items = Array.isArray(data) ? data : Object.entries(data).map(([trade, cost]) => ({ trade, cost }));
  const maxCost = Math.max(...items.map((i) => Number(i.cost || 0)), 1);
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <BarRow
          key={item.trade || i}
          label={item.trade || 'Overall'}
          value={`$${Number(item.cost || 0).toFixed(2)}`}
          maxValue={maxCost}
          suffix=""
        />
      ))}
    </div>
  );
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
      if (p.status === 'fulfilled') setPipeline(p.value);
      if (ep.status === 'fulfilled') setEmailPerf(ep.value);
      if (ab.status === 'fulfilled') setAbTests(ab.value);
      if (ac.status === 'fulfilled') setAgentCosts(ac.value);
      if (cpl.status === 'fulfilled') setCostPerLead(cpl.value);
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

  const emailPerfItems = Array.isArray(emailPerf)
    ? emailPerf
    : emailPerf
    ? Object.entries(emailPerf).map(([step, data]) => ({ step, ...data }))
    : [];

  const maxEmailOpen = Math.max(...emailPerfItems.map((e) => Number(e.open_rate || e.opens || 0)), 1);

  const agentCostItems = Array.isArray(agentCosts)
    ? agentCosts
    : agentCosts
    ? Object.entries(agentCosts).map(([agent, cost]) => ({ agent, cost }))
    : [];

  const maxAgentCost = Math.max(...agentCostItems.map((a) => Number(a.cost || a.total_cost || 0)), 1);

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

      {pipeline && (
        <SectionCard title="Pipeline Waterfall" icon={TrendingUp}>
          <FunnelChart stages={pipeline} />
        </SectionCard>
      )}

      {emailPerfItems.length > 0 && (
        <SectionCard title="Email Performance by Step" icon={BarChart3}>
          <div className="space-y-3">
            {emailPerfItems.map((item, i) => (
              <BarRow
                key={item.step ?? i}
                label={item.step != null ? `Step ${item.step}` : item.name || `Step ${i + 1}`}
                value={`${(Number(item.open_rate || item.opens || 0) * 100).toFixed(1)}%`}
                maxValue={maxEmailOpen}
              />
            ))}
          </div>
        </SectionCard>
      )}

      <SectionCard title="A/B Test Results" icon={FlaskConical}>
        <AbTestTable tests={Array.isArray(abTests) ? abTests : (abTests ? [abTests] : [])} />
      </SectionCard>

      {agentCostItems.length > 0 && (
        <SectionCard title="Agent Costs (Last 7 Days)" icon={Zap}>
          <div className="space-y-3">
            {agentCostItems.map((item, i) => (
              <BarRow
                key={item.agent || i}
                label={item.agent || `Agent ${i + 1}`}
                value={`$${Number(item.cost || item.total_cost || 0).toFixed(4)}`}
                maxValue={maxAgentCost}
              />
            ))}
          </div>
        </SectionCard>
      )}

      <SectionCard title="Cost Per Lead by Trade" icon={DollarSign}>
        <CostPerLeadSection data={costPerLead} />
      </SectionCard>
    </div>
  );
}
