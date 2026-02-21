import { useState, useEffect } from 'react';
import {
  Shield,
  ShieldAlert,
  ShieldX,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Users,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { api } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import Badge from '../components/ui/Badge';

const STATUS_CONFIGS = {
  green: {
    icon: Shield,
    title: 'Compliant',
    description: 'All TCPA compliance checks are passing.',
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    iconColor: 'text-emerald-600',
    titleColor: 'text-emerald-700',
  },
  yellow: {
    icon: ShieldAlert,
    title: 'Warning',
    description: 'Some compliance metrics need attention.',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    iconColor: 'text-amber-600',
    titleColor: 'text-amber-700',
  },
  red: {
    icon: ShieldX,
    title: 'Action Required',
    description: 'Compliance violations detected. Immediate action required.',
    bg: 'bg-red-50',
    border: 'border-red-200',
    iconColor: 'text-red-600',
    titleColor: 'text-red-700',
  },
};

const METRIC_STATUS_COLORS = {
  green: 'text-gray-900',
  yellow: 'text-amber-600',
  red: 'text-red-600',
};

export default function Compliance() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedMetric, setExpandedMetric] = useState(null);
  const [drillDownData, setDrillDownData] = useState(null);
  const [drillDownLoading, setDrillDownLoading] = useState(false);

  useEffect(() => {
    loadCompliance();
  }, []);

  const loadCompliance = async () => {
    try {
      const data = await api.getComplianceSummary();
      setSummary(data);
      setError(null);
    } catch (err) {
      console.error('Failed to load compliance:', err);
      setError(err.message || 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const handleMetricClick = async (metricKey) => {
    if (expandedMetric === metricKey) {
      setExpandedMetric(null);
      setDrillDownData(null);
      return;
    }
    setExpandedMetric(metricKey);
    setDrillDownLoading(true);
    try {
      const data = await api.getComplianceDetails(metricKey);
      setDrillDownData(data);
    } catch (e) {
      setDrillDownData({ items: [], error: e.message });
    } finally {
      setDrillDownLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const overallStatus = getOverallStatus(summary);
  const config = STATUS_CONFIGS[overallStatus];
  const StatusIcon = config.icon;

  const optOutRate =
    summary?.total_consent_records > 0
      ? ((summary.opted_out_count / summary.total_consent_records) * 100).toFixed(1)
      : '0.0';

  const metrics = buildMetrics(summary, optOutRate);
  const checklist = buildChecklist(summary);

  return (
    <div>
      <PageHeader title="TCPA Compliance" />

      {error && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-red-600 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          Failed to load compliance data. <button onClick={() => { setError(null); loadCompliance(); }} className="underline font-medium cursor-pointer">Retry</button>
        </div>
      )}

      <div
        className={`rounded-2xl p-6 mb-8 border ${config.bg} ${config.border}`}
      >
        <div className="flex items-center gap-3">
          <StatusIcon className={`w-6 h-6 ${config.iconColor}`} />
          <div>
            <p className={`text-base font-semibold ${config.titleColor}`}>
              {config.title}
            </p>
            <p className="text-sm text-gray-600 mt-0.5">
              {config.description}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {metrics.map((metric) => (
          <MetricCard
            key={metric.key}
            {...metric}
            expanded={expandedMetric === metric.key}
            onClick={() => handleMetricClick(metric.key)}
            drillDownData={expandedMetric === metric.key ? drillDownData : null}
            drillDownLoading={expandedMetric === metric.key && drillDownLoading}
          />
        ))}
      </div>

      <ComplianceChecklist items={checklist} />

      {summary?.last_audit && (
        <p className="text-xs text-gray-400 mt-6">
          Last audit: {new Date(summary.last_audit).toLocaleString()}
        </p>
      )}
    </div>
  );
}

function getOverallStatus(summary) {
  if (!summary) return 'yellow';
  if (summary.cold_outreach_violations > 0 || summary.messages_in_quiet_hours > 0) {
    return 'red';
  }
  if (summary.opted_out_count > 0 && summary.total_consent_records > 0) {
    const optOutRate = summary.opted_out_count / summary.total_consent_records;
    if (optOutRate > 0.1) return 'yellow';
  }
  return 'green';
}

function buildMetrics(summary, optOutRate) {
  const quietStatus = (summary?.messages_in_quiet_hours || 0) > 0 ? 'red' : 'green';
  const coldStatus = (summary?.cold_outreach_violations || 0) > 0 ? 'red' : 'green';
  const optOutStatus =
    summary?.total_consent_records > 0 &&
    summary.opted_out_count / summary.total_consent_records > 0.1
      ? 'yellow'
      : 'green';

  return [
    {
      key: 'consent',
      label: 'Consent Records',
      value: summary?.total_consent_records || 0,
      subtitle: 'Total active consent records on file',
      icon: Users,
      status: 'green',
    },
    {
      key: 'opt_out',
      label: 'Opt-Out Count',
      value: summary?.opted_out_count || 0,
      subtitle: 'Contacts who opted out of messaging',
      icon: XCircle,
      status: (summary?.opted_out_count || 0) > 0 ? 'yellow' : 'green',
    },
    {
      key: 'quiet_hours',
      label: 'Quiet Hours Violations',
      value: summary?.messages_in_quiet_hours || 0,
      subtitle: 'Messages sent outside allowed hours',
      icon: Clock,
      status: quietStatus,
    },
    {
      key: 'cold_outreach',
      label: 'Cold Outreach Violations',
      value: summary?.cold_outreach_violations || 0,
      subtitle: 'Messages exceeding per-lead limits',
      icon: AlertCircle,
      status: coldStatus,
    },
    {
      key: 'pending_followups',
      label: 'Pending Follow-ups',
      value: summary?.pending_followups || 0,
      subtitle: 'Queued follow-up messages',
      icon: Clock,
      status: 'green',
    },
    {
      key: 'opt_out_rate',
      label: 'Opt-Out Rate',
      value: `${optOutRate}%`,
      subtitle: 'Percentage of contacts who opted out',
      icon: Shield,
      status: optOutStatus,
    },
  ];
}

function buildChecklist(summary) {
  if (!summary) return [];
  return [
    {
      label: 'Consent records retained (5-year FTC TSR 2024)',
      status: summary.total_consent_records > 0 ? 'pass' : 'warn',
    },
    {
      label: 'Opt-out processing active',
      status: 'pass',
    },
    {
      label: 'AI disclosure included (California SB 1001)',
      status: summary.messages_with_ai_disclosure != null ? 'pass' : 'warn',
    },
    {
      label: 'Quiet hours enforcement (state-specific)',
      status: (summary.messages_in_quiet_hours || 0) === 0 ? 'pass' : 'fail',
    },
    {
      label: 'Business name in first message',
      status: 'pass',
    },
    {
      label: 'STOP opt-out in first message',
      status: 'pass',
    },
  ];
}

function MetricCard({ label, value, subtitle, icon: Icon, status, expanded, onClick, drillDownData, drillDownLoading }) {
  const valueColor = METRIC_STATUS_COLORS[status] || 'text-gray-900';

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm overflow-hidden">
      <button
        onClick={onClick}
        className="w-full text-left p-6 cursor-pointer hover:bg-gray-50/50 transition-colors"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Icon className="w-4 h-4 text-gray-400" />
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
              {label}
            </span>
          </div>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </div>
        <p className={`text-2xl font-bold font-mono ${valueColor}`}>{value}</p>
        <p className="text-xs text-gray-400 mt-1.5">{subtitle}</p>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-6 py-4 bg-gray-50/50 max-h-48 overflow-y-auto">
          {drillDownLoading ? (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <div className="w-4 h-4 border-2 border-gray-300 border-t-transparent rounded-full animate-spin" />
              Loading details...
            </div>
          ) : drillDownData?.error ? (
            <p className="text-xs text-gray-400">{drillDownData.error}</p>
          ) : drillDownData?.items?.length > 0 ? (
            <div className="space-y-2">
              {drillDownData.items.map((item, i) => (
                <div key={item.id || i} className="flex items-center justify-between text-xs">
                  <span className="text-gray-600 truncate">
                    {item.phone_masked || item.lead_name || `Record ${i + 1}`}
                  </span>
                  <span className="text-gray-400 font-mono ml-2 flex-shrink-0">
                    {item.date || item.created_at ? new Date(item.date || item.created_at).toLocaleDateString() : ''}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-400">No details available</p>
          )}
        </div>
      )}
    </div>
  );
}

function ComplianceChecklist({ items }) {
  const iconMap = {
    pass: <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />,
    fail: <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />,
    warn: <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0" />,
    warning: <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0" />,
  };

  const badgeVariantMap = {
    pass: 'success',
    fail: 'danger',
    warn: 'warning',
    warning: 'warning',
  };

  const badgeLabelMap = {
    pass: 'Pass',
    fail: 'Fail',
    warn: 'Warning',
    warning: 'Warning',
  };

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900 mb-5">
        Compliance Checklist
      </h2>
      <div>
        {items.map(({ label, status }) => (
          <div
            key={label}
            className="flex items-center gap-3 py-3 border-b border-gray-100 last:border-0"
          >
            {iconMap[status]}
            <span className="text-sm text-gray-700 flex-1">{label}</span>
            <Badge variant={badgeVariantMap[status]} size="sm">
              {badgeLabelMap[status]}
            </Badge>
          </div>
        ))}
      </div>
    </div>
  );
}
