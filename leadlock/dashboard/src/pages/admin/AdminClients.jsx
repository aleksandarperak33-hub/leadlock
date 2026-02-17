import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { Plus, X, ChevronLeft, ChevronRight } from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import SearchInput from '../../components/ui/SearchInput';
import DataTable from '../../components/ui/DataTable';
import Badge from '../../components/ui/Badge';

const INITIAL_FORM = {
  business_name: '', trade_type: 'hvac', tier: 'starter', monthly_fee: '497',
  owner_name: '', owner_email: '', owner_phone: '',
  dashboard_email: '', dashboard_password: '', crm_type: 'google_sheets',
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

/**
 * Maps a tier name to a Badge variant.
 */
const tierVariant = (tier) => {
  switch (tier) {
    case 'enterprise': return 'warning';
    case 'scale': return 'info';
    case 'growth': return 'success';
    case 'starter': return 'neutral';
    default: return 'neutral';
  }
};

const TABLE_COLUMNS = [
  {
    key: 'business_name',
    label: 'Business Name',
    render: (val) => (
      <span className="font-medium text-gray-900">{val}</span>
    ),
  },
  {
    key: 'trade_type',
    label: 'Trade',
    render: (val) => (
      <span className="capitalize text-gray-600">{val || '\u2014'}</span>
    ),
  },
  {
    key: 'tier',
    label: 'Tier',
    render: (val) => (
      <Badge variant={tierVariant(val)} size="sm">
        {val || 'none'}
      </Badge>
    ),
  },
  {
    key: 'billing_status',
    label: 'Billing',
    render: (val) => (
      <Badge variant={billingVariant(val)} size="sm">
        {(val || 'unknown').replace('_', ' ')}
      </Badge>
    ),
  },
  {
    key: 'leads_30d',
    label: 'Leads',
    align: 'right',
    render: (val) => (
      <span className="font-mono text-gray-900">{val ?? '\u2014'}</span>
    ),
  },
  {
    key: 'booked_30d',
    label: 'Booked',
    align: 'right',
    render: (val) => (
      <span className="font-mono text-emerald-600">{val ?? '\u2014'}</span>
    ),
  },
  {
    key: 'conversion_rate',
    label: 'Conversion %',
    align: 'right',
    render: (val) => (
      <span className="font-mono text-gray-600">
        {val != null ? `${(val * 100).toFixed(1)}%` : '\u2014'}
      </span>
    ),
  },
  {
    key: 'monthly_fee',
    label: 'MRR',
    align: 'right',
    render: (val) => (
      <span className="font-mono font-medium text-gray-900">
        ${val?.toLocaleString() || '0'}
      </span>
    ),
  },
];

const FORM_FIELDS = [
  { label: 'Business Name', key: 'business_name', type: 'text', placeholder: 'Austin Comfort HVAC', required: true },
  { label: 'Owner Name', key: 'owner_name', type: 'text', placeholder: 'John Smith' },
  { label: 'Owner Email', key: 'owner_email', type: 'email', placeholder: 'john@business.com' },
  { label: 'Owner Phone', key: 'owner_phone', type: 'text', placeholder: '+15551234567' },
  { label: 'Dashboard Email', key: 'dashboard_email', type: 'email', placeholder: 'john@business.com' },
  { label: 'Dashboard Password', key: 'dashboard_password', type: 'password', placeholder: 'Set login password' },
  { label: 'Monthly Fee', key: 'monthly_fee', type: 'number', placeholder: '497' },
];

export default function AdminClients() {
  const navigate = useNavigate();
  const [clients, setClients] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);
  const [saving, setSaving] = useState(false);

  const fetchClients = async () => {
    setLoading(true);
    try {
      const params = { page, per_page: 20 };
      if (search) params.search = search;
      const data = await api.getAdminClients(params);
      setClients(data.clients || []);
      setTotal(data.total || 0);
      setPages(data.pages || 1);
    } catch (e) {
      console.error('Failed to fetch clients:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchClients(); }, [page, search]);

  const handleCreate = async () => {
    setSaving(true);
    try {
      await api.createAdminClient({
        ...form,
        monthly_fee: Number(form.monthly_fee) || 497,
      });
      setShowForm(false);
      setForm(INITIAL_FORM);
      fetchClients();
    } catch (e) {
      console.error('Failed to create client:', e);
    } finally {
      setSaving(false);
    }
  };

  const handleSearchChange = (val) => {
    setSearch(val);
    setPage(1);
  };

  return (
    <div className="bg-[#FAFAFA] min-h-screen">
      <PageHeader
        title="Clients"
        actions={
          <div className="flex items-center gap-3">
            <div className="w-64">
              <SearchInput
                value={search}
                onChange={handleSearchChange}
                placeholder="Search clients..."
              />
            </div>
            <button
              onClick={() => { setForm(INITIAL_FORM); setShowForm(true); }}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer shadow-sm"
            >
              <Plus className="w-4 h-4" />
              New Client
            </button>
          </div>
        }
      />

      {/* New Client Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50 flex items-start justify-center pt-24">
          <div className="bg-white rounded-2xl p-8 max-w-lg w-full shadow-xl border border-gray-200/60">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-gray-900">New Client</h2>
              <button
                onClick={() => setShowForm(false)}
                className="text-gray-400 hover:text-gray-600 cursor-pointer transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 max-h-[70vh] overflow-y-auto">
              {FORM_FIELDS.map(({ label, key, type, placeholder, required }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                    {label}{required && ' *'}
                  </label>
                  <input
                    type={type}
                    value={form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl text-sm bg-white border border-gray-200 text-gray-900 placeholder-gray-400 outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100 transition-all"
                    placeholder={placeholder}
                  />
                </div>
              ))}

              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Trade Type', key: 'trade_type', options: ['hvac', 'plumbing', 'electrical', 'roofing', 'solar', 'general'] },
                  { label: 'Tier', key: 'tier', options: ['starter', 'growth', 'scale', 'enterprise'] },
                  { label: 'CRM', key: 'crm_type', options: ['google_sheets', 'service_titan', 'housecall_pro', 'jobber', 'gohighlevel'] },
                ].map(({ label, key, options }) => (
                  <div key={key}>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      {label}
                    </label>
                    <select
                      value={form[key]}
                      onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                      className="w-full px-3 py-2.5 rounded-xl text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100 transition-all cursor-pointer"
                    >
                      {options.map(t => (
                        <option key={t} value={t}>
                          {t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-3 pt-2">
                <button
                  onClick={() => setShowForm(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={saving || !form.business_name || !form.trade_type}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shadow-sm"
                >
                  {saving ? 'Creating...' : 'Create Client'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-14 rounded-2xl bg-gray-100 animate-pulse" />
          ))}
        </div>
      ) : (
        <DataTable
          columns={TABLE_COLUMNS}
          data={clients}
          emptyMessage="No clients found"
          onRowClick={(row) => navigate(`/clients/${row.id}`)}
        />
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-xs font-mono text-gray-400">
            Page {page} of {pages} ({total} total)
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-white border border-transparent hover:border-gray-200/60 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage(p => Math.min(pages, p + 1))}
              disabled={page === pages}
              className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-white border border-transparent hover:border-gray-200/60 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
