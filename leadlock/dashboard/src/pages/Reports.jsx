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
      <div className="space-y-4">
        <div className="h-6 w-40 rounded-lg bg-gray-100 animate-pulse" />
        <div className="h-96 rounded-xl bg-gray-100 animate-pulse" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-xl font-semibold tracking-tight text-gray-900">Weekly Report</h1>
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium text-gray-600 bg-white border border-gray-200 shadow-sm hover:bg-gray-50 transition-colors cursor-pointer"
        >
          <Printer className="w-4 h-4" />
          Print
        </button>
      </div>

      {report && (
        <div className="space-y-6">
          {/* Summary */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Total Leads', value: report.total_leads, color: 'orange' },
              { label: 'Booked', value: report.total_booked ?? 0, sub: `${((report.conversion_rate ?? 0) * 100).toFixed(1)}% conversion`, color: 'emerald' },
              { label: 'Avg Response', value: `${((report.avg_response_time_ms ?? 0) / 1000).toFixed(1)}s`, color: 'amber' },
              { label: 'Total Cost', value: `$${((report.total_ai_cost ?? 0) + (report.total_sms_cost ?? 0)).toFixed(2)}`, sub: `AI: $${(report.total_ai_cost ?? 0).toFixed(2)} | SMS: $${(report.total_sms_cost ?? 0).toFixed(2)}`, color: 'orange2' },
            ].map(({ label, value, sub, color }) => {
              const colorMap = {
                orange: 'bg-orange-50 border-orange-100 text-orange-600',
                emerald: 'bg-emerald-50 border-emerald-100 text-emerald-600',
                amber: 'bg-amber-50 border-amber-100 text-amber-600',
                orange2: 'bg-orange-50 border-orange-100 text-orange-600',
              };
              const dotMap = {
                orange: 'bg-orange-500',
                emerald: 'bg-emerald-500',
                amber: 'bg-amber-500',
                orange2: 'bg-orange-500',
              };
              return (
                <div key={label} className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <div className={`w-1.5 h-1.5 rounded-full ${dotMap[color]}`} />
                    <p className="text-xs font-medium uppercase tracking-wider text-gray-500">{label}</p>
                  </div>
                  <p className="text-2xl font-bold font-mono text-gray-900">{value}</p>
                  {sub && <p className="text-xs text-gray-400 mt-1.5">{sub}</p>}
                </div>
              );
            })}
          </div>

          {/* Leads by source */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Leads by Source</h3>
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-2.5 text-xs font-semibold uppercase tracking-wider text-gray-400">Source</th>
                  <th className="text-right py-2.5 text-xs font-semibold uppercase tracking-wider text-gray-400">Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.leads_by_source || {}).sort((a, b) => b[1] - a[1]).map(([source, count]) => (
                  <tr key={source} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="py-2.5 text-sm capitalize text-gray-600">{source.replace('_', ' ')}</td>
                    <td className="py-2.5 text-sm text-right font-mono font-medium text-gray-900">{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Leads by state */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Leads by State</h3>
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-2.5 text-xs font-semibold uppercase tracking-wider text-gray-400">State</th>
                  <th className="text-right py-2.5 text-xs font-semibold uppercase tracking-wider text-gray-400">Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.leads_by_state || {}).sort((a, b) => b[1] - a[1]).map(([state, count]) => (
                  <tr key={state} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="py-2.5 text-sm capitalize text-gray-600">{state.replace('_', ' ')}</td>
                    <td className="py-2.5 text-sm text-right font-mono font-medium text-gray-900">{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Response time distribution */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Response Time Distribution</h3>
            <div className="grid grid-cols-4 gap-3">
              {(report.response_time_distribution || []).map(bucket => {
                const colorMap = {
                  '0-10s': { bg: 'bg-emerald-50', border: 'border-emerald-100', text: 'text-emerald-600' },
                  '10-30s': { bg: 'bg-orange-50', border: 'border-orange-100', text: 'text-orange-600' },
                  '30-60s': { bg: 'bg-amber-50', border: 'border-amber-100', text: 'text-amber-600' },
                };
                const colors = colorMap[bucket.bucket] || { bg: 'bg-red-50', border: 'border-red-100', text: 'text-red-600' };
                return (
                  <div key={bucket.bucket} className={`text-center p-4 rounded-xl border ${colors.bg} ${colors.border}`}>
                    <p className={`text-xl font-bold font-mono ${colors.text}`}>{bucket.count}</p>
                    <p className="text-xs text-gray-500 mt-1">{bucket.bucket}</p>
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
