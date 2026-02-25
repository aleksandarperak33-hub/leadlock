import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { ArrowLeft, Users, Calendar, Clock, TrendingUp } from 'lucide-react';
import StatCard from '../../components/ui/StatCard';
import Badge from '../../components/ui/Badge';
import DataTable from '../../components/ui/DataTable';

/**
 * Maps a lead state to a Badge variant.
 */
const stateVariant = (state) => {
  switch (state) {
    case 'booked':
    case 'completed':
      return 'success';
    case 'qualified':
    case 'qualifying':
      return 'info';
    case 'new':
    case 'intake_sent':
      return 'warning';
    case 'cold':
    case 'dead':
    case 'opted_out':
      return 'danger';
    default:
      return 'neutral';
  }
};

/**
 * Maps a billing status to a Badge variant.
 */
const billingVariant = (status) => {
  switch (status) {
    case 'active': return 'success';
    case 'trial': return 'info';
    case 'past_due': return 'warning';
    case 'cancelled': return 'danger';
    default: return 'neutral';
  }
};

const LEAD_COLUMNS = [
  {
    key: 'name',
    label: 'Name',
    render: (_val, row) => (
      <span className="font-medium text-gray-900">
        {row.first_name || 'Unknown'} {row.last_name || ''}
      </span>
    ),
  },
  {
    key: 'phone_masked',
    label: 'Phone',
    render: (val) => (
      <span className="font-mono text-gray-500">{val || '\u2014'}</span>
    ),
  },
  {
    key: 'source',
    label: 'Source',
    render: (val) => (
      <span className="capitalize text-gray-600">
        {(val || '').replace('_', ' ') || '\u2014'}
      </span>
    ),
  },
  {
    key: 'state',
    label: 'Status',
    render: (val) => (
      <Badge variant={stateVariant(val)} size="sm">
        {(val || '').replace('_', ' ')}
      </Badge>
    ),
  },
  {
    key: 'score',
    label: 'Score',
    align: 'right',
    render: (val) => (
      <span className="font-mono text-gray-600">{val ?? '\u2014'}</span>
    ),
  },
  {
    key: 'created_at',
    label: 'Date',
    render: (val) => (
      <span className="font-mono text-xs text-gray-400">
        {val ? new Date(val).toLocaleDateString() : '\u2014'}
      </span>
    ),
  },
];

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
      <div className="bg-[#FAFAFA] min-h-screen space-y-6">
        <div className="h-6 w-48 bg-gray-100 rounded-lg animate-pulse" />
        <div className="h-40 bg-gray-100 rounded-2xl animate-pulse" />
        <div className="grid grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 rounded-2xl bg-gray-100 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-[#FAFAFA] min-h-screen flex flex-col items-center justify-center py-20">
        <p className="text-sm text-gray-400 mb-3">Client not found</p>
        <button
          onClick={() => navigate('/clients')}
          className="text-sm text-orange-500 hover:text-orange-600 cursor-pointer font-medium"
        >
          Back to clients
        </button>
      </div>
    );
  }

  const client = data.client || {};
  const metrics = data.metrics || {};
  const recentLeads = data.recent_leads || [];

  const infoFields = [
    { label: 'Email', value: client.owner_email || client.dashboard_email || '\u2014' },
    { label: 'Phone', value: client.owner_phone || client.twilio_phone || '\u2014' },
    { label: 'Twilio Phone', value: client.twilio_phone || '\u2014' },
    { label: '10DLC Status', value: client.ten_dlc_status || 'pending' },
    { label: 'CRM Type', value: client.crm_type || '\u2014' },
    { label: 'Created', value: client.created_at ? new Date(client.created_at).toLocaleDateString() : '\u2014' },
  ];

  return (
    <div className="bg-[#FAFAFA] min-h-screen">
      {/* Back button */}
      <button
        onClick={() => navigate('/clients')}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 cursor-pointer mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Clients
      </button>

      {/* Client Info Header */}
      <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">{client.business_name}</h1>
            <p className="text-sm text-gray-500 capitalize mt-0.5">
              {client.trade_type || 'Unknown trade'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={tierVariant(client.tier)} size="md">
              {client.tier || 'none'}
            </Badge>
            <Badge variant={billingVariant(client.billing_status)} size="md">
              {(client.billing_status || 'unknown').replace('_', ' ')}
            </Badge>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 pt-4 border-t border-gray-100">
          {infoFields.map(({ label, value }) => (
            <div key={label}>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</p>
              <p className="text-sm font-mono mt-1 capitalize text-gray-700">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
        <StatCard
          label="Total Leads"
          value={metrics.total_leads ?? '\u2014'}
          icon={Users}
          color="brand"
        />
        <StatCard
          label="Booked"
          value={metrics.total_booked ?? '\u2014'}
          icon={Calendar}
          color="green"
        />
        <StatCard
          label="Avg Response"
          value={
            metrics.avg_response_ms
              ? `${(metrics.avg_response_ms / 1000).toFixed(1)}s`
              : '\u2014'
          }
          icon={Clock}
          color="yellow"
        />
        <StatCard
          label="Conversion %"
          value={
            metrics.conversion_rate != null
              ? `${(metrics.conversion_rate * 100).toFixed(1)}%`
              : '\u2014'
          }
          icon={TrendingUp}
          color="brand"
        />
      </div>

      {/* Recent Leads */}
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Leads</h3>
        <DataTable
          columns={LEAD_COLUMNS}
          data={recentLeads}
          emptyMessage="No leads yet"
        />
      </div>
    </div>
  );
}

/**
 * Maps a tier name to a Badge variant (duplicated locally for self-containment).
 */
function tierVariant(tier) {
  switch (tier) {
    case 'enterprise': return 'warning';
    case 'scale': return 'info';
    case 'growth': return 'success';
    case 'starter': return 'neutral';
    default: return 'neutral';
  }
}
