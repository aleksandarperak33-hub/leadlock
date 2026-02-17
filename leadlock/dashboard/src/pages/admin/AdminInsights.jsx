import { useState, useEffect } from 'react';
import { LineChart, TrendingUp, Clock, Target, BarChart3 } from 'lucide-react';
import { api } from '../../api/client';
import PageHeader from '../../components/ui/PageHeader';
import EmptyState from '../../components/ui/EmptyState';

function BarRow({ label, value, count }) {
  const pct = Math.round((value ?? 0) * 100);

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-700 capitalize w-32 shrink-0">
        {label}
      </span>
      <div className="flex-1 h-3 rounded-full overflow-hidden bg-orange-100">
        <div
          className="h-full bg-orange-500 rounded-full transition-all duration-500"
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      <span className="text-sm font-mono text-gray-900 w-14 text-right">
        {pct}%
      </span>
      <span className="text-xs text-gray-400 w-14 text-right font-mono">
        n={count}
      </span>
    </div>
  );
}

function InsightSection({ title, icon: Icon, children }) {
  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm mb-6">
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

export default function AdminInsights() {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInsights();
  }, []);

  const loadInsights = async () => {
    try {
      const data = await api.getInsights();
      setInsights(data);
    } catch {
      // API not yet implemented
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

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <PageHeader
        title="Insights"
        subtitle={`${insights?.total_signals || 0} signals collected (last 30 days)`}
      />

      {!insights || insights.total_signals === 0 ? (
        <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm">
          <EmptyState
            icon={LineChart}
            title="No insights yet"
            description="Insights will populate as emails are sent and engagement is tracked."
          />
        </div>
      ) : (
        <div>
          {insights.open_rate_by_trade?.length > 0 && (
            <InsightSection title="Open Rate by Trade" icon={Target}>
              <div className="space-y-3">
                {insights.open_rate_by_trade.map((item) => (
                  <BarRow
                    key={item.trade}
                    label={item.trade}
                    value={item.open_rate}
                    count={item.count}
                  />
                ))}
              </div>
            </InsightSection>
          )}

          {insights.open_rate_by_time?.length > 0 && (
            <InsightSection title="Best Send Times" icon={Clock}>
              <div className="space-y-3">
                {insights.open_rate_by_time.map((item) => (
                  <BarRow
                    key={item.time_bucket}
                    label={item.time_bucket}
                    value={item.open_rate}
                    count={item.count}
                  />
                ))}
              </div>
            </InsightSection>
          )}

          {insights.open_rate_by_step?.length > 0 && (
            <InsightSection title="Open Rate by Step" icon={BarChart3}>
              <div className="space-y-3">
                {insights.open_rate_by_step.map((item) => (
                  <BarRow
                    key={item.step}
                    label={`Step ${item.step}`}
                    value={item.open_rate}
                    count={item.count}
                  />
                ))}
              </div>
            </InsightSection>
          )}

          {insights.reply_rate_by_trade?.length > 0 && (
            <InsightSection title="Reply Rate by Trade" icon={TrendingUp}>
              <div className="space-y-3">
                {insights.reply_rate_by_trade.map((item) => (
                  <BarRow
                    key={item.trade}
                    label={item.trade}
                    value={item.reply_rate}
                    count={item.count}
                  />
                ))}
              </div>
            </InsightSection>
          )}
        </div>
      )}
    </div>
  );
}
