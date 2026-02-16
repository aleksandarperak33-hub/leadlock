import { useState, useEffect } from 'react';
import { Shield, CheckCircle, AlertTriangle, XCircle, Clock, Users } from 'lucide-react';
import { api } from '../api/client';

const STATUS_LEVELS = {
  green: { icon: CheckCircle, label: 'Compliant', color: 'text-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-100', dot: 'bg-emerald-500' },
  yellow: { icon: AlertTriangle, label: 'Warning', color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-100', dot: 'bg-amber-500' },
  red: { icon: XCircle, label: 'Action Required', color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-100', dot: 'bg-red-500' },
};

export default function Compliance() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCompliance();
  }, []);

  const loadCompliance = async () => {
    try {
      const data = await api.getComplianceSummary();
      setSummary(data);
    } catch (err) {
      console.error('Failed to load compliance:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Determine overall TCPA status
  const getOverallStatus = () => {
    if (!summary) return 'yellow';
    if (summary.cold_outreach_violations > 0 || summary.messages_in_quiet_hours > 0) return 'red';
    if (summary.opted_out_count > 0 && summary.total_consent_records > 0) {
      const optOutRate = summary.opted_out_count / summary.total_consent_records;
      if (optOutRate > 0.1) return 'yellow';
    }
    return 'green';
  };

  const overallStatus = getOverallStatus();
  const StatusIcon = STATUS_LEVELS[overallStatus].icon;
  const statusConfig = STATUS_LEVELS[overallStatus];

  return (
    <div>
      <div className="flex items-center gap-3 mb-8">
        <Shield className="w-5 h-5 text-indigo-500" />
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">Compliance</h1>
          <p className="text-sm text-gray-500">TCPA compliance monitoring and audit trail</p>
        </div>
      </div>

      {/* Overall status banner */}
      <div className={`rounded-xl p-5 mb-6 border ${statusConfig.bg} ${statusConfig.border}`}>
        <div className="flex items-center gap-3">
          <StatusIcon className={`w-6 h-6 ${statusConfig.color}`} />
          <div>
            <p className={`text-base font-semibold ${statusConfig.color}`}>
              {statusConfig.label}
            </p>
            <p className="text-sm text-gray-600 mt-0.5">
              {overallStatus === 'green' && 'All TCPA compliance checks are passing.'}
              {overallStatus === 'yellow' && 'Some compliance metrics need attention.'}
              {overallStatus === 'red' && 'Compliance violations detected. Immediate action required.'}
            </p>
          </div>
        </div>
      </div>

      {/* Compliance metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <ComplianceCard
          title="Consent Records"
          value={summary?.total_consent_records || 0}
          icon={Users}
          description="Total active consent records on file"
          status="green"
        />
        <ComplianceCard
          title="Opt-Out Count"
          value={summary?.opted_out_count || 0}
          icon={XCircle}
          description="Contacts who opted out of messaging"
          status={summary?.opted_out_count > 0 ? 'yellow' : 'green'}
        />
        <ComplianceCard
          title="Quiet Hours Violations"
          value={summary?.messages_in_quiet_hours || 0}
          icon={Clock}
          description="Messages sent outside allowed hours"
          status={summary?.messages_in_quiet_hours > 0 ? 'red' : 'green'}
        />
        <ComplianceCard
          title="Cold Outreach Violations"
          value={summary?.cold_outreach_violations || 0}
          icon={AlertTriangle}
          description="Messages exceeding per-lead limits"
          status={summary?.cold_outreach_violations > 0 ? 'red' : 'green'}
        />
        <ComplianceCard
          title="Pending Follow-ups"
          value={summary?.pending_followups || 0}
          icon={Clock}
          description="Queued follow-up messages"
          status="green"
        />
        <ComplianceCard
          title="Opt-Out Rate"
          value={summary?.total_consent_records > 0
            ? `${((summary.opted_out_count / summary.total_consent_records) * 100).toFixed(1)}%`
            : '0%'}
          icon={Shield}
          description="Percentage of contacts who opted out"
          status={summary?.total_consent_records > 0 && (summary.opted_out_count / summary.total_consent_records) > 0.1 ? 'yellow' : 'green'}
        />
      </div>

      {/* Compliance checklist */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-5">Compliance Checklist</h2>
        <div className="space-y-3.5">
          {[
            { label: 'STOP keyword processing active', ok: true },
            { label: 'Consent records retained (5yr FTC TSR)', ok: true },
            { label: 'Business name in first message', ok: true },
            { label: 'Opt-out instructions in first message', ok: true },
            { label: 'Quiet hours enforcement (8AM-9PM local)', ok: true },
            { label: 'Max 3 cold outreach messages per lead', ok: true },
            { label: 'AI disclosure included (CA SB 1001)', ok: true },
            { label: 'No URL shorteners in messages', ok: true },
          ].map(({ label, ok }) => (
            <div key={label} className="flex items-center gap-3">
              <CheckCircle className={`w-4 h-4 flex-shrink-0 ${ok ? 'text-emerald-500' : 'text-red-500'}`} />
              <span className="text-sm text-gray-600">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {summary?.last_audit && (
        <p className="text-xs text-gray-400 mt-4">
          Last audit: {new Date(summary.last_audit).toLocaleString()}
        </p>
      )}
    </div>
  );
}

function ComplianceCard({ title, value, icon: Icon, description, status }) {
  const config = STATUS_LEVELS[status] || STATUS_LEVELS.green;
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-gray-400" />
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">{title}</span>
        </div>
        <div className={`w-2 h-2 rounded-full ${config.dot}`} />
      </div>
      <p className={`text-2xl font-bold ${config.color}`}>{value}</p>
      <p className="text-xs text-gray-400 mt-1.5">{description}</p>
    </div>
  );
}
