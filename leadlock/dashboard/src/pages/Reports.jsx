import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { BarChart3, DollarSign, Clock, Users, CalendarCheck, Printer } from 'lucide-react';

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
        <div className="h-8 w-48 bg-slate-800 rounded animate-pulse" />
        <div className="h-96 bg-slate-900 border border-slate-800 rounded-xl animate-pulse" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Weekly Report</h1>
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 text-slate-300 rounded-lg text-sm hover:bg-slate-700 transition-colors"
        >
          <Printer className="w-4 h-4" />
          Print Report
        </button>
      </div>

      {report && (
        <div className="space-y-6">
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-medium mb-2">
                <Users className="w-4 h-4" /> Total Leads
              </div>
              <p className="text-2xl font-bold text-white">{report.total_leads}</p>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-medium mb-2">
                <CalendarCheck className="w-4 h-4" /> Booked
              </div>
              <p className="text-2xl font-bold text-emerald-400">{report.total_booked}</p>
              <p className="text-xs text-slate-500 mt-1">{(report.conversion_rate * 100).toFixed(1)}% conversion</p>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-medium mb-2">
                <Clock className="w-4 h-4" /> Avg Response
              </div>
              <p className="text-2xl font-bold text-white">{(report.avg_response_time_ms / 1000).toFixed(1)}s</p>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-medium mb-2">
                <DollarSign className="w-4 h-4" /> Total Cost
              </div>
              <p className="text-2xl font-bold text-white">
                ${(report.total_ai_cost + report.total_sms_cost).toFixed(2)}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                AI: ${report.total_ai_cost.toFixed(2)} | SMS: ${report.total_sms_cost.toFixed(2)}
              </p>
            </div>
          </div>

          {/* Leads by source table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="text-sm font-medium text-slate-400 mb-4">Leads by Source</h3>
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-2 text-xs font-medium text-slate-500">Source</th>
                  <th className="text-right py-2 text-xs font-medium text-slate-500">Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.leads_by_source || {}).sort((a, b) => b[1] - a[1]).map(([source, count]) => (
                  <tr key={source} className="border-b border-slate-800/50">
                    <td className="py-2 text-sm text-slate-300 capitalize">{source.replace('_', ' ')}</td>
                    <td className="py-2 text-sm text-white text-right font-medium">{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Leads by state table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="text-sm font-medium text-slate-400 mb-4">Leads by State</h3>
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-2 text-xs font-medium text-slate-500">State</th>
                  <th className="text-right py-2 text-xs font-medium text-slate-500">Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.leads_by_state || {}).sort((a, b) => b[1] - a[1]).map(([state, count]) => (
                  <tr key={state} className="border-b border-slate-800/50">
                    <td className="py-2 text-sm text-slate-300 capitalize">{state.replace('_', ' ')}</td>
                    <td className="py-2 text-sm text-white text-right font-medium">{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Response time distribution */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="text-sm font-medium text-slate-400 mb-4">Response Time Distribution</h3>
            <div className="grid grid-cols-4 gap-3">
              {(report.response_time_distribution || []).map(bucket => (
                <div key={bucket.bucket} className="text-center p-3 bg-slate-800 rounded-lg">
                  <p className="text-lg font-bold text-white">{bucket.count}</p>
                  <p className="text-xs text-slate-400">{bucket.bucket}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
