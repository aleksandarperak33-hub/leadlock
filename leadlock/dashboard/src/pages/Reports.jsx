import { useState, useEffect } from 'react';
import { Users, CalendarCheck, Clock, DollarSign, Printer, AlertCircle } from 'lucide-react';
import { api } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import StatCard from '../components/ui/StatCard';

const RESPONSE_TIME_COLORS = {
  '0-10s': {
    value: 'text-emerald-600',
    label: 'text-emerald-600',
    bg: 'bg-emerald-50',
    border: 'border-emerald-100',
  },
  '10-30s': {
    value: 'text-orange-600',
    label: 'text-orange-600',
    bg: 'bg-orange-50',
    border: 'border-orange-100',
  },
  '30-60s': {
    value: 'text-amber-600',
    label: 'text-amber-600',
    bg: 'bg-amber-50',
    border: 'border-amber-100',
  },
};

const DEFAULT_RESPONSE_COLORS = {
  value: 'text-red-600',
  label: 'text-red-600',
  bg: 'bg-red-50',
  border: 'border-red-100',
};

const PERIOD_OPTIONS = [
  { id: '7d', label: '7 Days' },
  { id: '30d', label: '30 Days' },
  { id: '90d', label: '90 Days' },
  { id: 'custom', label: 'Custom' },
];

export default function Reports() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState('7d');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');

  const fetchReport = async () => {
    setLoading(true);
    try {
      let data;
      if (period === 'custom' && customStart && customEnd) {
        data = await api.getCustomReport(customStart, customEnd);
      } else if (period !== 'custom') {
        data = await api.getWeeklyReport(period === '7d' ? undefined : period);
      } else {
        setLoading(false);
        return;
      }
      setReport(data);
      setError(null);
    } catch (e) {
      console.error('Failed to fetch report:', e);
      setError(e.message || 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, [period]);

  const handleCustomApply = () => {
    if (customStart && customEnd) fetchReport();
  };

  if (loading && !report) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-40 rounded-lg bg-gray-100 animate-pulse" />
        <div className="h-96 rounded-xl bg-gray-100 animate-pulse" />
      </div>
    );
  }

  const totalCost =
    (report?.total_ai_cost ?? 0) + (report?.total_sms_cost ?? 0);
  const hasResponseData = (report?.avg_response_time_ms ?? 0) > 0 || (report?.total_leads ?? 0) > 0;
  const avgResponseSec = hasResponseData
    ? ((report?.avg_response_time_ms ?? 0) / 1000).toFixed(1)
    : 'N/A';
  const conversionPct = ((report?.conversion_rate ?? 0) * 100).toFixed(1);

  const headerActions = (
    <div className="flex items-center gap-3">
      <div className="flex rounded-xl p-1 bg-gray-100/80 border border-gray-200/50">
        {PERIOD_OPTIONS.map((p) => (
          <button
            key={p.id}
            onClick={() => setPeriod(p.id)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              period === p.id
                ? 'bg-white text-orange-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <button
        onClick={() => window.print()}
        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-gray-600 bg-white border border-gray-200 shadow-sm hover:bg-gray-50 transition-colors cursor-pointer"
      >
        <Printer className="w-4 h-4" />
        Print
      </button>
    </div>
  );

  return (
    <div>
      <PageHeader title="Reports" actions={headerActions} />

      {/* Custom date range picker */}
      {period === 'custom' && (
        <div className="flex items-end gap-3 mb-6 p-4 bg-white border border-gray-200/50 rounded-xl">
          <div>
            <label htmlFor="report-start" className="text-xs font-medium text-gray-500 mb-1 block">Start Date</label>
            <input
              id="report-start"
              type="date"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100"
            />
          </div>
          <div>
            <label htmlFor="report-end" className="text-xs font-medium text-gray-500 mb-1 block">End Date</label>
            <input
              id="report-end"
              type="date"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100"
            />
          </div>
          <button
            onClick={handleCustomApply}
            disabled={!customStart || !customEnd}
            className="px-5 py-2 rounded-lg text-sm font-medium bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer"
          >
            Apply
          </button>
        </div>
      )}

      {error && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-red-600 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          Failed to load report data. <button onClick={() => { setError(null); fetchReport(); }} className="underline font-medium cursor-pointer">Retry</button>
        </div>
      )}

      {report && (
        <div className="space-y-8">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard
              label="Total Leads"
              value={report.total_leads}
              icon={Users}
              color="brand"
            />
            <StatCard
              label="Booked"
              value={report.total_booked ?? 0}
              deltaLabel={`${conversionPct}% conversion`}
              icon={CalendarCheck}
              color="green"
            />
            <StatCard
              label="Avg Response Time"
              value={hasResponseData ? `${avgResponseSec}s` : 'N/A'}
              icon={Clock}
              color="yellow"
            />
            <StatCard
              label="Total Cost"
              value={`$${totalCost.toFixed(2)}`}
              deltaLabel={`AI: $${(report.total_ai_cost ?? 0).toFixed(2)} | SMS: $${(report.total_sms_cost ?? 0).toFixed(2)}`}
              icon={DollarSign}
              color="brand"
            />
          </div>

          <SourceTable
            title="Leads by Source"
            entries={report.leads_by_source}
          />

          <SourceTable
            title="Leads by State"
            entries={report.leads_by_state}
          />

          <ResponseTimeDistribution
            buckets={report.response_time_distribution}
            totalLeads={report.total_leads}
          />
        </div>
      )}
    </div>
  );
}

function SourceTable({ title, entries }) {
  const sorted = Object.entries(entries || {}).sort((a, b) => b[1] - a[1]);

  return (
    <div className="bg-white border border-gray-200/50 rounded-2xl shadow-card overflow-hidden">
      <div className="px-6 pt-6 pb-4">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
      </div>
      <table className="w-full">
        <thead>
          <tr className="bg-gray-50/80 border-b border-gray-200/50">
            <th scope="col" className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
              {title.includes('Source') ? 'Source' : 'State'}
            </th>
            <th scope="col" className="text-right px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
              Count
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(([name, count]) => (
            <tr
              key={name}
              className="border-b border-gray-100 last:border-0 hover:bg-gray-50/50 transition-colors"
            >
              <td className="px-6 py-3.5 text-sm capitalize text-gray-600">
                {name.replaceAll('_', ' ')}
              </td>
              <td className="px-6 py-3.5 text-sm text-right font-mono font-medium text-gray-900">
                {count}
              </td>
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={2} className="px-6 py-8 text-center text-sm text-gray-400">
                No data available
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ResponseTimeDistribution({ buckets, totalLeads }) {
  if (!buckets || buckets.length === 0) return null;

  return (
    <div>
      <h3 className="text-lg font-semibold text-gray-900 mb-4">
        Response Time Distribution
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {buckets.map((bucket) => {
          const colors =
            RESPONSE_TIME_COLORS[bucket.bucket] || DEFAULT_RESPONSE_COLORS;
          const percentage =
            totalLeads > 0
              ? ((bucket.count / totalLeads) * 100).toFixed(1)
              : '0.0';

          return (
            <div
              key={bucket.bucket}
              className="bg-white border border-gray-200/50 rounded-xl p-4"
            >
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                {bucket.bucket}
              </p>
              <p className={`text-2xl font-bold font-mono ${colors.value}`}>
                {bucket.count}
              </p>
              <p className="text-xs text-gray-400 mt-1">
                <span className="font-mono">{percentage}%</span> of leads
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
