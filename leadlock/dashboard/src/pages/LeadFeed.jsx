import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import LeadStatusBadge from '../components/LeadStatusBadge';
import { Search, Clock, ChevronLeft, ChevronRight } from 'lucide-react';

const STATE_FILTERS = ['all', 'new', 'qualifying', 'qualified', 'booked', 'cold', 'opted_out'];

export default function LeadFeed() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [stateFilter, setStateFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchLeads = async () => {
    try {
      const params = { page, per_page: 20 };
      if (stateFilter !== 'all') params.state = stateFilter;
      if (search) params.search = search;

      const data = await api.getLeads(params);
      setLeads(data.leads || []);
      setTotal(data.total || 0);
      setPages(data.pages || 1);
    } catch (e) {
      console.error('Failed to fetch leads:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchLeads();
    const interval = setInterval(fetchLeads, 15000);
    return () => clearInterval(interval);
  }, [page, stateFilter, search]);

  const responseTimeColor = (ms) => {
    if (!ms) return 'var(--text-tertiary)';
    if (ms < 10000) return '#34d399';
    if (ms < 60000) return '#fbbf24';
    return '#f87171';
  };

  return (
    <div className="animate-fade-up">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Leads</h1>
        <span className="text-[12px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{total} total</span>
      </div>

      {/* Search */}
      <div className="mb-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} />
          <input
            type="text"
            placeholder="Search name, phone, service..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full pl-9 pr-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
            style={{ color: 'var(--text-primary)' }}
          />
        </div>
      </div>

      {/* Filter chips */}
      <div className="flex gap-1.5 mb-4 overflow-x-auto pb-1">
        {STATE_FILTERS.map(s => (
          <button
            key={s}
            onClick={() => { setStateFilter(s); setPage(1); }}
            className="px-2.5 py-1 text-[11px] font-medium rounded-lg whitespace-nowrap transition-all duration-200"
            style={{
              background: stateFilter === s ? 'var(--accent-muted)' : 'transparent',
              color: stateFilter === s ? 'var(--accent)' : 'var(--text-tertiary)',
              border: stateFilter === s ? '1px solid rgba(99, 102, 241, 0.2)' : '1px solid var(--border)',
            }}
          >
            {s === 'all' ? 'All' : s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)', background: 'rgba(255, 255, 255, 0.02)' }}>
                {['Name', 'Phone', 'Source', 'Status', 'Score', 'Service', 'Response', 'Date'].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && leads.length === 0 ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td colSpan={8} className="px-4 py-3.5">
                      <div className="h-3.5 rounded-lg animate-pulse" style={{ background: 'var(--surface-2)' }} />
                    </td>
                  </tr>
                ))
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-[13px]" style={{ color: 'var(--text-tertiary)' }}>
                    No leads found
                  </td>
                </tr>
              ) : leads.map(lead => (
                <tr
                  key={lead.id}
                  onClick={() => navigate(`/conversations/${lead.id}`)}
                  className="cursor-pointer transition-all duration-150"
                  style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td className="px-4 py-2.5 text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                    {lead.first_name || 'Unknown'} {lead.last_name || ''}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{lead.phone_masked}</td>
                  <td className="px-4 py-2.5 text-[12px] capitalize" style={{ color: 'var(--text-tertiary)' }}>{lead.source?.replace('_', ' ')}</td>
                  <td className="px-4 py-2.5"><LeadStatusBadge status={lead.state} /></td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="w-10 rounded-full h-1" style={{ background: 'var(--surface-3)' }}>
                        <div
                          className="h-1 rounded-full"
                          style={{
                            width: `${lead.score}%`,
                            background: lead.score >= 70 ? '#34d399' : lead.score >= 40 ? '#fbbf24' : '#f87171',
                            opacity: 0.75,
                          }}
                        />
                      </div>
                      <span className="text-[11px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{lead.score}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-[12px] max-w-[120px] truncate" style={{ color: 'var(--text-tertiary)' }}>{lead.service_type || '\u2014'}</td>
                  <td className="px-4 py-2.5">
                    {lead.first_response_ms ? (
                      <span className="text-[11px] font-mono font-medium flex items-center gap-1" style={{ color: responseTimeColor(lead.first_response_ms) }}>
                        <Clock className="w-3 h-3" />
                        {(lead.first_response_ms / 1000).toFixed(1)}s
                      </span>
                    ) : (
                      <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>\u2014</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-[11px] font-mono" style={{ color: 'var(--text-tertiary)' }}>
                    {new Date(lead.created_at).toLocaleDateString()}
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
                className="p-1.5 rounded-lg transition-colors disabled:opacity-20"
                style={{ color: 'var(--text-tertiary)' }}
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage(p => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="p-1.5 rounded-lg transition-colors disabled:opacity-20"
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
