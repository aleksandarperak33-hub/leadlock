import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { Search, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';

export default function AdminClients() {
  const navigate = useNavigate();
  const [clients, setClients] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
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
    fetchClients();
  }, [page, search]);

  const billingColor = (status) => {
    switch (status) {
      case 'active': return '#34d399';
      case 'trial': return '#fbbf24';
      case 'past_due': return '#f87171';
      default: return 'var(--text-tertiary)';
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Clients</h1>
        <span className="text-[12px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{total} total</span>
      </div>

      {/* Search */}
      <div className="mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} />
          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            className="w-full pl-9 pr-4 py-2 rounded-md text-[13px] outline-none transition-colors"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            onFocus={e => e.target.style.borderColor = 'var(--border-active)'}
            onBlur={e => e.target.style.borderColor = 'var(--border)'}
          />
        </div>
      </div>

      {/* Table */}
      <div className="rounded-card overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Business', 'Trade', 'Tier', 'Billing', 'Leads (30d)', 'Booked', 'Conversion', 'MRR'].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
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
                    ${client.mrr?.toLocaleString() || '0'}
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
