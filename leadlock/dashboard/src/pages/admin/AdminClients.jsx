import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { Search, ChevronLeft, ChevronRight, Plus, X } from 'lucide-react';

const inputStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
};

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

  const billingColor = (status) => {
    switch (status) {
      case 'active': return '#34d399';
      case 'trial': return '#fbbf24';
      case 'past_due': return '#f87171';
      default: return 'var(--text-tertiary)';
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
    <div className="animate-fade-up">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Clients</h1>
        <div className="flex items-center gap-3">
          <span className="text-[12px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{total} total</span>
          <button
            onClick={() => { setForm(INITIAL_FORM); setShowForm(true); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold text-white transition-all gradient-btn"
          >
            <Plus className="w-3.5 h-3.5" />
            New Client
          </button>
        </div>
      </div>

      {/* New Client Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl p-6 glass-card gradient-border">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-[15px] font-semibold" style={{ color: 'var(--text-primary)' }}>New Client</h2>
              <button onClick={() => setShowForm(false)} style={{ color: 'var(--text-tertiary)' }}>
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
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>
                    {label}{required && ' *'}
                  </label>
                  <input
                    type={type}
                    value={form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md text-[13px] outline-none"
                    style={inputStyle}
                    placeholder={placeholder}
                  />
                </div>
              ))}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Trade Type</label>
                  <select value={form.trade_type} onChange={e => setForm(f => ({ ...f, trade_type: e.target.value }))} className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle}>
                    {['hvac', 'plumbing', 'electrical', 'roofing', 'solar', 'general'].map(t => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Tier</label>
                  <select value={form.tier} onChange={e => setForm(f => ({ ...f, tier: e.target.value }))} className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle}>
                    {['starter', 'growth', 'scale', 'enterprise'].map(t => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>CRM</label>
                  <select value={form.crm_type} onChange={e => setForm(f => ({ ...f, crm_type: e.target.value }))} className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle}>
                    {['google_sheets', 'service_titan', 'housecall_pro', 'jobber', 'gohighlevel'].map(t => (
                      <option key={t} value={t}>{t.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                    ))}
                  </select>
                </div>
              </div>
              <button
                onClick={handleCreate}
                disabled={saving || !form.business_name || !form.trade_type}
                className="w-full py-2.5 rounded-md text-[13px] font-medium text-white transition-all disabled:opacity-50"
                style={{ background: 'var(--accent)' }}
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
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} />
          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            className="w-full pl-9 pr-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
            style={{ color: 'var(--text-primary)' }}
          />
        </div>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)', background: 'rgba(255, 255, 255, 0.02)' }}>
                {['Business', 'Trade', 'Tier', 'Billing', 'Leads (30d)', 'Booked', 'Conversion', 'MRR'].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td colSpan={8} className="px-4 py-3.5">
                      <div className="h-3.5 rounded animate-pulse" style={{ background: 'var(--surface-2)' }} />
                    </td>
                  </tr>
                ))
              ) : clients.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-[13px]" style={{ color: 'var(--text-tertiary)' }}>
                    No clients found
                  </td>
                </tr>
              ) : clients.map(client => (
                <tr
                  key={client.id}
                  onClick={() => navigate(`/clients/${client.id}`)}
                  className="cursor-pointer transition-colors"
                  style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td className="px-4 py-2.5 text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                    {client.business_name}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] capitalize" style={{ color: 'var(--text-tertiary)' }}>
                    {client.trade_type || '—'}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] capitalize" style={{ color: 'var(--text-tertiary)' }}>
                    {client.tier || '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="text-[11px] font-medium capitalize px-1.5 py-0.5 rounded"
                      style={{
                        color: billingColor(client.billing_status),
                        background: `${billingColor(client.billing_status)}15`,
                      }}
                    >
                      {(client.billing_status || 'unknown').replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-primary)' }}>
                    {client.leads_30d ?? '—'}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: '#34d399' }}>
                    {client.booked_30d ?? '—'}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
                    {client.conversion_rate != null ? `${(client.conversion_rate * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                    ${client.monthly_fee?.toLocaleString() || '0'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-2.5" style={{ borderTop: '1px solid var(--border)' }}>
            <span className="text-[11px] font-mono" style={{ color: 'var(--text-tertiary)' }}>Page {page} of {pages}</span>
            <div className="flex gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1 rounded transition-colors disabled:opacity-20"
                style={{ color: 'var(--text-tertiary)' }}
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage(p => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="p-1 rounded transition-colors disabled:opacity-20"
                style={{ color: 'var(--text-tertiary)' }}
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
