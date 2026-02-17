import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { Search, ChevronLeft, ChevronRight, Plus, X } from 'lucide-react';

const INITIAL_FORM = {
  business_name: '', trade_type: 'hvac', tier: 'starter', monthly_fee: '497',
  owner_name: '', owner_email: '', owner_phone: '',
  dashboard_email: '', dashboard_password: '', crm_type: 'google_sheets',
};

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

  const billingBadge = (status) => {
    switch (status) {
      case 'active': return 'bg-emerald-50 text-emerald-700 border-emerald-100';
      case 'trial': return 'bg-amber-50 text-amber-700 border-amber-100';
      case 'past_due': return 'bg-red-50 text-red-700 border-red-100';
      default: return 'bg-gray-50 text-gray-500 border-gray-100';
    }
  };

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

  return (
    <div style={{ background: '#f8f9fb' }}>
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold tracking-tight text-gray-900">Clients</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-gray-400">{total} total</span>
          <button
            onClick={() => { setForm(INITIAL_FORM); setShowForm(true); }}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-white bg-orange-600 hover:bg-orange-700 transition-colors cursor-pointer shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            New Client
          </button>
        </div>
      </div>

      {/* New Client Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl p-6 bg-white border border-gray-200 shadow-xl">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold text-gray-900">New Client</h2>
              <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600 cursor-pointer transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 max-h-[70vh] overflow-y-auto">
              {[
                { label: 'Business Name', key: 'business_name', type: 'text', placeholder: 'Austin Comfort HVAC', required: true },
                { label: 'Owner Name', key: 'owner_name', type: 'text', placeholder: 'John Smith' },
                { label: 'Owner Email', key: 'owner_email', type: 'email', placeholder: 'john@business.com' },
                { label: 'Owner Phone', key: 'owner_phone', type: 'text', placeholder: '+15551234567' },
                { label: 'Dashboard Email', key: 'dashboard_email', type: 'email', placeholder: 'john@business.com' },
                { label: 'Dashboard Password', key: 'dashboard_password', type: 'password', placeholder: 'Set login password' },
                { label: 'Monthly Fee', key: 'monthly_fee', type: 'number', placeholder: '497' },
              ].map(({ label, key, type, placeholder, required }) => (
                <div key={key}>
                  <label className="block text-xs font-medium uppercase tracking-wider mb-1.5 text-gray-500">
                    {label}{required && ' *'}
                  </label>
                  <input
                    type={type}
                    value={form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 placeholder-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-all"
                    placeholder={placeholder}
                  />
                </div>
              ))}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider mb-1.5 text-gray-500">Trade Type</label>
                  <select
                    value={form.trade_type}
                    onChange={e => setForm(f => ({ ...f, trade_type: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-all cursor-pointer"
                  >
                    {['hvac', 'plumbing', 'electrical', 'roofing', 'solar', 'general'].map(t => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider mb-1.5 text-gray-500">Tier</label>
                  <select
                    value={form.tier}
                    onChange={e => setForm(f => ({ ...f, tier: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-all cursor-pointer"
                  >
                    {['starter', 'growth', 'scale', 'enterprise'].map(t => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider mb-1.5 text-gray-500">CRM</label>
                  <select
                    value={form.crm_type}
                    onChange={e => setForm(f => ({ ...f, crm_type: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-all cursor-pointer"
                  >
                    {['google_sheets', 'service_titan', 'housecall_pro', 'jobber', 'gohighlevel'].map(t => (
                      <option key={t} value={t}>{t.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                    ))}
                  </select>
                </div>
              </div>
              <button
                onClick={handleCreate}
                disabled={saving || !form.business_name || !form.trade_type}
                className="w-full py-2.5 rounded-lg text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shadow-sm"
              >
                {saving ? 'Creating...' : 'Create Client'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            className="w-full pl-10 pr-4 py-2.5 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 placeholder-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-all"
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {['Business', 'Trade', 'Tier', 'Billing', 'Leads (30d)', 'Booked', 'Conversion', 'MRR'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    <td colSpan={8} className="px-4 py-4">
                      <div className="h-4 rounded bg-gray-100 animate-pulse" />
                    </td>
                  </tr>
                ))
              ) : clients.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-sm text-gray-400">
                    No clients found
                  </td>
                </tr>
              ) : clients.map(client => (
                <tr
                  key={client.id}
                  onClick={() => navigate(`/clients/${client.id}`)}
                  className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors"
                >
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {client.business_name}
                  </td>
                  <td className="px-4 py-3 text-sm capitalize text-gray-500">
                    {client.trade_type || '\u2014'}
                  </td>
                  <td className="px-4 py-3 text-sm capitalize text-gray-500">
                    {client.tier || '\u2014'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium capitalize px-2 py-0.5 rounded-md border ${billingBadge(client.billing_status)}`}>
                      {(client.billing_status || 'unknown').replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-900">
                    {client.leads_30d ?? '\u2014'}
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-emerald-600">
                    {client.booked_30d ?? '\u2014'}
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-500">
                    {client.conversion_rate != null ? `${(client.conversion_rate * 100).toFixed(1)}%` : '\u2014'}
                  </td>
                  <td className="px-4 py-3 text-sm font-mono font-medium text-gray-900">
                    ${client.monthly_fee?.toLocaleString() || '0'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
            <span className="text-xs font-mono text-gray-400">Page {page} of {pages}</span>
            <div className="flex gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage(p => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
