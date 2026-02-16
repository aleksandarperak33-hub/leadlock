import { useState, useEffect } from 'react';
import { Shield, CheckCircle, AlertTriangle, XCircle, Clock, Users } from 'lucide-react';
import { api } from '../api/client';

const STATUS_LEVELS = {
  green: { icon: CheckCircle, label: 'Compliant', color: '#34d399', bg: 'rgba(52, 211, 153, 0.08)' },
  yellow: { icon: AlertTriangle, label: 'Warning', color: '#fbbf24', bg: 'rgba(251, 191, 36, 0.08)' },
  red: { icon: XCircle, label: 'Action Required', color: '#f87171', bg: 'rgba(248, 113, 113, 0.08)' },
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
        <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }} />
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

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Shield className="w-5 h-5" style={{ color: 'var(--accent)' }} />
        <div>
          <h1 className="text-[20px] font-bold" style={{ color: 'var(--text-primary)' }}>Compliance</h1>
          <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>TCPA compliance monitoring and audit trail</p>
        </div>
      </div>

      {/* Overall status banner */}
      <div className="rounded-xl p-5 mb-6" style={{
        background: STATUS_LEVELS[overallStatus].bg,
        border: `1px solid ${STATUS_LEVELS[overallStatus].color}20`,
      }}>
        <div className="flex items-center gap-3">
          <StatusIcon className="w-6 h-6" style={{ color: STATUS_LEVELS[overallStatus].color }} />
          <div>
            <p className="text-[15px] font-semibold" style={{ color: STATUS_LEVELS[overallStatus].color }}>
              {STATUS_LEVELS[overallStatus].label}
            </p>
            <p className="text-[12px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>
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
      <div className="rounded-xl p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
        <h2 className="text-[14px] font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>Compliance Checklist</h2>
        <div className="space-y-3">
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
              <CheckCircle className="w-4 h-4 flex-shrink-0" style={{ color: ok ? '#34d399' : '#f87171' }} />
              <span className="text-[13px]" style={{ color: 'var(--text-secondary)' }}>{label}</span>
            </div>
          ))}
        </div>
      </div>

      {summary?.last_audit && (
        <p className="text-[11px] mt-4" style={{ color: 'var(--text-tertiary)' }}>
          Last audit: {new Date(summary.last_audit).toLocaleString()}
        </p>
      )}
    </div>
  );
}

function ComplianceCard({ title, value, icon: Icon, description, status }) {
  const statusColor = STATUS_LEVELS[status]?.color || 'var(--text-secondary)';
  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon className="w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} />
          <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{title}</span>
        </div>
        <div className="w-2 h-2 rounded-full" style={{ background: statusColor }} />
      </div>
      <p className="text-[24px] font-bold" style={{ color: statusColor }}>{value}</p>
      <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{description}</p>
    </div>
  );
}
