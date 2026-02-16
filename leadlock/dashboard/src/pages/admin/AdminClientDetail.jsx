import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { ArrowLeft, Users, Calendar, TrendingUp, Clock } from 'lucide-react';

const BILLING_BADGE_STYLES = {
  active: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  trial: 'bg-amber-50 text-amber-700 border border-amber-100',
  past_due: 'bg-red-50 text-red-700 border border-red-100',
};

const STATE_BADGE_STYLES = {
  booked: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  completed: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  qualified: 'bg-blue-50 text-blue-700 border border-blue-100',
  qualifying: 'bg-blue-50 text-blue-700 border border-blue-100',
  new: 'bg-amber-50 text-amber-700 border border-amber-100',
  intake_sent: 'bg-amber-50 text-amber-700 border border-amber-100',
  cold: 'bg-red-50 text-red-700 border border-red-100',
  dead: 'bg-red-50 text-red-700 border border-red-100',
  opted_out: 'bg-red-50 text-red-700 border border-red-100',
};

const METRIC_ACCENTS = {
  'Total Leads': 'border-l-violet-500',
  'Booked': 'border-l-emerald-500',
  'Conversion': 'border-l-blue-500',
  'MRR': 'border-l-amber-500',
};

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
        <div className="h-6 w-48 bg-gray-100 rounded animate-pulse" />
        <div className="h-64 bg-gray-100 rounded-xl animate-pulse" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-20">
        <p className="text-sm text-gray-400">Client not found</p>
        <button
          onClick={() => navigate('/clients')}
          className="text-xs mt-2 text-violet-600 hover:text-violet-700 cursor-pointer"
        >
          Back to clients
        </button>
      </div>
    );
  }

  const client = data.client || {};
  const metrics = data.metrics || {};
  const recentLeads = data.recent_leads || [];

  const billingBadge = BILLING_BADGE_STYLES[client.billing_status] || 'bg-gray-50 text-gray-500 border border-gray-100';
  const getStateBadge = (state) => STATE_BADGE_STYLES[state] || 'bg-gray-50 text-gray-500 border border-gray-100';

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#f8f9fb' }}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/clients')}
          className="p-1.5 rounded-lg border border-gray-200 bg-white text-gray-400 hover:text-gray-600 hover:border-gray-300 transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-gray-900">
            {client.business_name}
          </h1>
          <p className="text-xs text-gray-400 capitalize">
            {client.trade_type || 'Unknown trade'} &middot; {client.tier || 'No tier'}
          </p>
        </div>
        <span className={`ml-auto text-xs font-medium capitalize px-2.5 py-0.5 rounded-md ${billingBadge}`}>
          {(client.billing_status || 'unknown').replace('_', ' ')}
        </span>
      </div>

      {/* Client Info */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 mb-4">
        <h3 className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">
          Client Information
        </h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Twilio Phone', value: client.twilio_phone || '\u2014' },
            { label: '10DLC Status', value: client.ten_dlc_status || 'pending' },
            { label: 'CRM Type', value: client.crm_type || '\u2014' },
            { label: 'Created', value: client.created_at ? new Date(client.created_at).toLocaleDateString() : '\u2014' },
          ].map(({ label, value }) => (
            <div key={label}>
              <p className="text-xs text-gray-400">{label}</p>
              <p className="text-sm font-mono mt-0.5 capitalize text-gray-600">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Total Leads', value: metrics.total_leads ?? '\u2014' },
          { label: 'Booked', value: metrics.total_booked ?? '\u2014' },
          { label: 'Conversion', value: metrics.conversion_rate != null ? `${(metrics.conversion_rate * 100).toFixed(1)}%` : '\u2014' },
          { label: 'MRR', value: `$${client.monthly_fee?.toLocaleString() || '0'}` },
        ].map(({ label, value }) => (
          <div
            key={label}
            className={`bg-white border border-gray-200 rounded-xl shadow-sm relative overflow-hidden p-4 border-l-2 ${METRIC_ACCENTS[label] || 'border-l-gray-300'}`}
          >
            <p className="text-xs font-medium uppercase tracking-wider text-gray-400">{label}</p>
            <p className="text-xl font-semibold font-mono mt-1 text-gray-900">{value}</p>
          </div>
        ))}
      </div>

      {/* Recent Leads */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100">
          <h3 className="text-xs font-medium uppercase tracking-wider text-gray-400">
            Recent Leads
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {['Name', 'Phone', 'State', 'Source', 'Score', 'Date'].map(h => (
                  <th
                    key={h}
                    className="text-left px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-gray-500"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentLeads.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-gray-400">
                    No leads yet
                  </td>
                </tr>
              ) : recentLeads.map(lead => (
                <tr key={lead.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 text-sm font-medium text-gray-900">
                    {lead.first_name || 'Unknown'} {lead.last_name || ''}
                  </td>
                  <td className="px-4 py-2.5 text-xs font-mono text-gray-400">
                    {lead.phone_masked || '\u2014'}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs font-medium capitalize px-2 py-0.5 rounded-md ${getStateBadge(lead.state)}`}>
                      {(lead.state || '').replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs capitalize text-gray-400">
                    {(lead.source || '').replace('_', ' ')}
                  </td>
                  <td className="px-4 py-2.5 text-xs font-mono text-gray-400">
                    {lead.score ?? '\u2014'}
                  </td>
                  <td className="px-4 py-2.5 text-xs font-mono text-gray-400">
                    {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '\u2014'}
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
