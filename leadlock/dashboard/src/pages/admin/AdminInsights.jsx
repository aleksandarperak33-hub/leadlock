import { useState, useEffect } from 'react';
import { LineChart, TrendingUp, Clock, Target, BarChart3 } from 'lucide-react';
import { api } from '../../api/client';

const BAR_COLORS = {
  blue: { bar: 'bg-blue-500', text: 'text-blue-600' },
  emerald: { bar: 'bg-emerald-500', text: 'text-emerald-600' },
  orange: { bar: 'bg-orange-500', text: 'text-orange-600' },
  amber: { bar: 'bg-amber-500', text: 'text-amber-600' },
};

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
        <div className="w-6 h-6 border-2 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-orange-50">
          <LineChart className="w-4.5 h-4.5 text-orange-600" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Learning Insights</h1>
          <p className="text-sm text-gray-500">
            {insights?.total_signals || 0} signals collected (last 30 days)
          </p>
        </div>
      </div>

      {!insights || insights.total_signals === 0 ? (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm text-center py-16">
          <LineChart className="w-10 h-10 mx-auto mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-700">No insights yet</p>
          <p className="text-xs text-gray-400 mt-1">
            Insights will populate as emails are sent and engagement is tracked.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Open Rate by Trade */}
          {insights.open_rate_by_trade?.length > 0 && (
            <InsightSection title="Open Rate by Trade" icon={Target}>
              <div className="space-y-3">
                {insights.open_rate_by_trade.map(item => (
                  <BarRow key={item.trade} label={item.trade} value={item.open_rate} count={item.count} color="blue" />
                ))}
              </div>
            </InsightSection>
          )}

          {/* Open Rate by Time */}
          {insights.open_rate_by_time?.length > 0 && (
            <InsightSection title="Best Send Times" icon={Clock}>
              <div className="space-y-3">
                {insights.open_rate_by_time.map(item => (
                  <BarRow key={item.time_bucket} label={item.time_bucket} value={item.open_rate} count={item.count} color="emerald" />
                ))}
              </div>
            </InsightSection>
          )}

          {/* Open Rate by Step */}
          {insights.open_rate_by_step?.length > 0 && (
            <InsightSection title="Open Rate by Sequence Step" icon={BarChart3}>
              <div className="space-y-3">
                {insights.open_rate_by_step.map(item => (
                  <BarRow key={item.step} label={`Step ${item.step}`} value={item.open_rate} count={item.count} color="orange" />
                ))}
              </div>
            </InsightSection>
          )}

          {/* Reply Rate by Trade */}
          {insights.reply_rate_by_trade?.length > 0 && (
            <InsightSection title="Reply Rate by Trade" icon={TrendingUp}>
              <div className="space-y-3">
                {insights.reply_rate_by_trade.map(item => (
                  <BarRow key={item.trade} label={item.trade} value={item.reply_rate} count={item.count} color="amber" />
                ))}
              </div>
            </InsightSection>
          )}
        </div>
      )}
    </div>
  );
}

function InsightSection({ title, icon: Icon, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-4 h-4 text-gray-400" />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function BarRow({ label, value, count, color }) {
  const pct = Math.round(value * 100);
  const colorSet = BAR_COLORS[color] || BAR_COLORS.blue;

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-medium capitalize w-28 flex-shrink-0 text-gray-700">{label}</span>
      <div className="flex-1 h-5 rounded-full overflow-hidden bg-gray-100">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colorSet.bar}`}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      <span className={`text-xs font-mono font-semibold w-12 text-right ${colorSet.text}`}>{pct}%</span>
      <span className="text-[10px] text-gray-400 w-12 text-right">n={count}</span>
    </div>
  );
}
