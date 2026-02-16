import { useState, useEffect } from 'react';
import { LineChart, TrendingUp, Clock, Target, BarChart3 } from 'lucide-react';
import { api } from '../../api/client';

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
        <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: '#a855f7', borderTopColor: 'transparent' }} />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <LineChart className="w-5 h-5" style={{ color: '#a855f7' }} />
        <div>
          <h1 className="text-[20px] font-bold" style={{ color: 'var(--text-primary)' }}>Learning Insights</h1>
          <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>
            {insights?.total_signals || 0} signals collected (last 30 days)
          </p>
        </div>
      </div>

      {!insights || insights.total_signals === 0 ? (
        <div className="text-center py-16 rounded-xl" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <LineChart className="w-10 h-10 mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }} />
          <p className="text-[14px] font-medium" style={{ color: 'var(--text-secondary)' }}>No insights yet</p>
          <p className="text-[12px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
            Insights will populate as emails are sent and engagement is tracked.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Open Rate by Trade */}
          {insights.open_rate_by_trade?.length > 0 && (
            <InsightSection title="Open Rate by Trade" icon={Target}>
              <div className="space-y-2">
                {insights.open_rate_by_trade.map(item => (
                  <BarRow key={item.trade} label={item.trade} value={item.open_rate} count={item.count} color="#60a5fa" />
                ))}
              </div>
            </InsightSection>
          )}

          {/* Open Rate by Time */}
          {insights.open_rate_by_time?.length > 0 && (
            <InsightSection title="Best Send Times" icon={Clock}>
              <div className="space-y-2">
                {insights.open_rate_by_time.map(item => (
                  <BarRow key={item.time_bucket} label={item.time_bucket} value={item.open_rate} count={item.count} color="#34d399" />
                ))}
              </div>
            </InsightSection>
          )}

          {/* Open Rate by Step */}
          {insights.open_rate_by_step?.length > 0 && (
            <InsightSection title="Open Rate by Sequence Step" icon={BarChart3}>
              <div className="space-y-2">
                {insights.open_rate_by_step.map(item => (
                  <BarRow key={item.step} label={`Step ${item.step}`} value={item.open_rate} count={item.count} color="#a855f7" />
                ))}
              </div>
            </InsightSection>
          )}

          {/* Reply Rate by Trade */}
          {insights.reply_rate_by_trade?.length > 0 && (
            <InsightSection title="Reply Rate by Trade" icon={TrendingUp}>
              <div className="space-y-2">
                {insights.reply_rate_by_trade.map(item => (
                  <BarRow key={item.trade} label={item.trade} value={item.reply_rate} count={item.count} color="#fbbf24" />
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
    <div className="rounded-xl p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
        <h2 className="text-[13px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{title}</h2>
      </div>
      {children}
    </div>
  );
}

function BarRow({ label, value, count, color }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-3">
      <span className="text-[12px] font-medium capitalize w-28 flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <div className="flex-1 h-5 rounded-full overflow-hidden" style={{ background: 'var(--surface-2)' }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%`, background: color }} />
      </div>
      <span className="text-[12px] font-mono font-medium w-12 text-right" style={{ color }}>{pct}%</span>
      <span className="text-[10px] w-12 text-right" style={{ color: 'var(--text-tertiary)' }}>n={count}</span>
    </div>
  );
}
