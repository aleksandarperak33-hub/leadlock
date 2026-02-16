import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { ArrowLeft, Users, Calendar, TrendingUp, Clock } from 'lucide-react';

export default function AdminClientDetail() {
  const { clientId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchClient = async () => {
      try {
        const result = await api.getAdminClient(clientId);
        setData(result);
      } catch (e) {
        console.error('Failed to fetch client:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchClient();
  }, [clientId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-48 rounded animate-pulse" style={{ background: 'var(--surface-2)' }} />
        <div className="h-64 rounded-card animate-pulse" style={{ background: 'var(--surface-1)' }} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-20">
        <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>Client not found</p>
        <button onClick={() => navigate('/clients')} className="text-[12px] mt-2" style={{ color: 'var(--accent)' }}>
          Back to clients
        </button>
      </div>
    );
  }

  const client = data.client || {};
  const metrics = data.metrics || {};
  const recentLeads = data.recent_leads || [];

  const billingColor = (status) => {
    switch (status) {
      case 'active': return '#34d399';
      case 'trial': return '#fbbf24';
      case 'past_due': return '#f87171';
      default: return 'var(--text-tertiary)';
    }
  };

  const stateColor = (state) => {
    switch (state) {
      case 'booked': case 'completed': return '#34d399';
      case 'qualified': case 'qualifying': return '#5a72f0';
      case 'new': case 'intake_sent': return '#fbbf24';
      case 'cold': case 'dead': return '#f87171';
      case 'opted_out': return '#ef4444';
      default: return 'var(--text-tertiary)';
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/clients')}
          className="p-1.5 rounded-md transition-colors"
          style={{ color: 'var(--text-tertiary)', background: 'var(--surface-2)' }}
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>{client.business_name}</h1>
          <p className="text-[12px] capitalize" style={{ color: 'var(--text-tertiary)' }}>
            {client.trade_type || 'Unknown trade'} &middot; {client.tier || 'No tier'}
          </p>
        </div>
        <span
          className="ml-auto text-[11px] font-medium capitalize px-2 py-0.5 rounded"
          style={{
            color: billingColor(client.billing_status),
            background: `${billingColor(client.billing_status)}15`,
          }}
        >
          {(client.billing_status || 'unknown').replace('_', ' ')}
        </span>
      </div>

      {/* Client Info */}
      <div className="rounded-card p-5 mb-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
        <h3 className="text-[11px] font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>Client Information</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Twilio Phone', value: client.twilio_phone || '—' },
            { label: '10DLC Status', value: client.ten_dlc_status || 'pending' },
            { label: 'CRM Type', value: client.crm_type || '—' },
            { label: 'Created', value: client.created_at ? new Date(client.created_at).toLocaleDateString() : '—' },
          ].map(({ label, value }) => (
            <div key={label}>
              <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
              <p className="text-[13px] font-mono mt-0.5 capitalize" style={{ color: 'var(--text-secondary)' }}>{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Total Leads', value: metrics.total_leads ?? '—', accent: '#7c5bf0' },
          { label: 'Booked', value: metrics.total_booked ?? '—', accent: '#34d399' },
          { label: 'Conversion', value: metrics.conversion_rate != null ? `${(metrics.conversion_rate * 100).toFixed(1)}%` : '—', accent: '#5a72f0' },
          { label: 'MRR', value: `$${client.monthly_fee?.toLocaleString() || '0'}`, accent: '#fbbf24' },
        ].map(({ label, value, accent }) => (
          <div
            key={label}
            className="relative overflow-hidden rounded-card p-4"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
          >
            <div className="absolute left-0 top-3 bottom-3 w-[2px] rounded-full" style={{ background: accent, opacity: 0.6 }} />
            <div className="pl-2.5">
              <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
              <p className="text-xl font-semibold font-mono mt-1" style={{ color: 'var(--text-primary)' }}>{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Recent Leads */}
      <div className="rounded-card overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
        <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <h3 className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Recent Leads</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Name', 'Phone', 'State', 'Source', 'Score', 'Date'].map(h => (
                  <th key={h} className="text-left px-4 py-2 text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentLeads.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-[12px]" style={{ color: 'var(--text-tertiary)' }}>
                    No leads yet
                  </td>
                </tr>
              ) : recentLeads.map(lead => (
                <tr key={lead.id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="px-4 py-2.5 text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                    {lead.first_name || 'Unknown'} {lead.last_name || ''}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
                    {lead.phone_masked || '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="text-[11px] font-medium capitalize px-1.5 py-0.5 rounded"
                      style={{ color: stateColor(lead.state), background: `${stateColor(lead.state)}15` }}>
                      {(lead.state || '').replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-[12px] capitalize" style={{ color: 'var(--text-tertiary)' }}>
                    {(lead.source || '').replace('_', ' ')}
                  </td>
                  <td className="px-4 py-2.5 text-[11px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
                    {lead.score ?? '—'}
                  </td>
                  <td className="px-4 py-2.5 text-[11px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
                    {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
