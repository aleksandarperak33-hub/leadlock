import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Printer } from 'lucide-react';

export default function Reports() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const data = await api.getWeeklyReport();
        setReport(data);
      } catch (e) {
        console.error('Failed to fetch report:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchReport();
  }, []);

  if (loading) {
    return (
      <div className="space-y-4 animate-fade-up">
        <div className="h-6 w-40 rounded-lg animate-pulse" style={{ background: 'var(--surface-2)' }} />
        <div className="h-96 rounded-xl animate-pulse" style={{ background: 'var(--surface-1)' }} />
      </div>
    );
  }

  return (
    <div className="animate-fade-up">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Weekly Report</h1>
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[12px] font-medium transition-all duration-200 glass"
          style={{ color: 'var(--text-secondary)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
        >
          <Printer className="w-3.5 h-3.5" />
          Print
        </button>
      </div>

      {report && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { label: 'Total Leads', value: report.total_leads, accent: '#6366f1' },
              { label: 'Booked', value: report.total_booked ?? 0, sub: `${((report.conversion_rate ?? 0) * 100).toFixed(1)}% conversion`, accent: '#34d399' },
              { label: 'Avg Response', value: `${((report.avg_response_time_ms ?? 0) / 1000).toFixed(1)}s`, accent: '#fbbf24' },
              { label: 'Total Cost', value: `$${((report.total_ai_cost ?? 0) + (report.total_sms_cost ?? 0)).toFixed(2)}`, sub: `AI: $${(report.total_ai_cost ?? 0).toFixed(2)} | SMS: $${(report.total_sms_cost ?? 0).toFixed(2)}`, accent: '#a78bfa' },
            ].map(({ label, value, sub, accent }) => (
              <div key={label} className="glass-card gradient-border relative overflow-hidden p-4">
                <div className="absolute left-0 top-3 bottom-3 w-[2px] rounded-full" style={{ background: `linear-gradient(180deg, ${accent}, transparent)`, opacity: 0.6 }} />
                <div className="pl-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
                  <p className="text-xl font-bold font-mono mt-1" style={{ color: 'var(--text-primary)' }}>{value}</p>
                  {sub && <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>}
                </div>
              </div>
            ))}
          </div>

          {/* Leads by source */}
          <div className="glass-card gradient-border p-5">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>Leads by Source</h3>
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th className="text-left py-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Source</th>
                  <th className="text-right py-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.leads_by_source || {}).sort((a, b) => b[1] - a[1]).map(([source, count]) => (
                  <tr key={source} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="py-2 text-[13px] capitalize" style={{ color: 'var(--text-secondary)' }}>{source.replace('_', ' ')}</td>
                    <td className="py-2 text-[13px] text-right font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Leads by state */}
          <div className="glass-card gradient-border p-5">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>Leads by State</h3>
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th className="text-left py-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>State</th>
                  <th className="text-right py-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.leads_by_state || {}).sort((a, b) => b[1] - a[1]).map(([state, count]) => (
                  <tr key={state} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="py-2 text-[13px] capitalize" style={{ color: 'var(--text-secondary)' }}>{state.replace('_', ' ')}</td>
                    <td className="py-2 text-[13px] text-right font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Response time distribution */}
          <div className="glass-card gradient-border p-5">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>Response Time Distribution</h3>
            <div className="grid grid-cols-4 gap-2">
              {(report.response_time_distribution || []).map(bucket => {
                const color = bucket.bucket === '0-10s' ? '#34d399' :
                              bucket.bucket === '10-30s' ? '#6366f1' :
                              bucket.bucket === '30-60s' ? '#fbbf24' : '#f87171';
                return (
                  <div key={bucket.bucket} className="text-center p-3 rounded-xl" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                    <p className="text-lg font-bold font-mono" style={{ color }}>{bucket.count}</p>
                    <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{bucket.bucket}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
