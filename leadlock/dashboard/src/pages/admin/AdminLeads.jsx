import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { Search, ChevronLeft, ChevronRight, Clock } from 'lucide-react';

const STATE_FILTERS = ['all', 'new', 'qualifying', 'qualified', 'booked', 'cold', 'opted_out'];

export default function AdminLeads() {
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [stateFilter, setStateFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLeads = async () => {
      setLoading(true);
      try {
        const params = { page, per_page: 25 };
        if (stateFilter !== 'all') params.state = stateFilter;
        if (search) params.search = search;
        const data = await api.getAdminLeads(params);
        setLeads(data.leads || []);
        setTotal(data.total || 0);
        setPages(data.pages || 1);
      } catch (e) {
        console.error('Failed to fetch admin leads:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchLeads();
  }, [page, stateFilter, search]);

  const stateBadge = (state) => {
    switch (state) {
      case 'booked': case 'completed':
        return 'bg-emerald-50 text-emerald-700 border-emerald-100';
      case 'qualified': case 'qualifying':
        return 'bg-blue-50 text-blue-700 border-blue-100';
      case 'new': case 'intake_sent':
        return 'bg-amber-50 text-amber-700 border-amber-100';
      case 'cold': case 'dead':
        return 'bg-red-50 text-red-600 border-red-100';
      case 'opted_out':
        return 'bg-red-50 text-red-700 border-red-100';
      default:
        return 'bg-gray-50 text-gray-500 border-gray-100';
    }
  };

  const responseTimeColor = (ms) => {
    if (!ms) return 'text-gray-400';
    if (ms < 10000) return 'text-emerald-600';
    if (ms < 60000) return 'text-amber-600';
    return 'text-red-600';
  };

  const scoreBarColor = (score) => {
    if (score >= 70) return 'bg-emerald-500';
    if (score >= 40) return 'bg-amber-500';
    return 'bg-red-500';
  };

  return (
    <div style={{ background: '#f8f9fb' }}>
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold tracking-tight text-gray-900">All Leads</h1>
        <span className="text-xs font-mono text-gray-400">{total} total</span>
      </div>

      {/* Search */}
      <div className="mb-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search name, phone, service, client..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            className="w-full pl-10 pr-4 py-2.5 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 placeholder-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-all"
          />
        </div>
      </div>

      {/* State filters */}
      <div className="flex gap-1.5 mb-4 overflow-x-auto pb-1">
        {STATE_FILTERS.map(s => (
          <button
            key={s}
            onClick={() => { setStateFilter(s); setPage(1); }}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all cursor-pointer border ${
              stateFilter === s
                ? 'bg-orange-50 text-orange-700 border-orange-200'
                : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50 hover:text-gray-700'
            }`}
          >
            {s === 'all' ? 'All' : s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {['Name', 'Client', 'Phone', 'Source', 'Status', 'Score', 'Response', 'Date'].map(h => (
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
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-sm text-gray-400">
                    No leads found
                  </td>
                </tr>
              ) : leads.map(lead => (
                <tr key={lead.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {lead.first_name || 'Unknown'} {lead.last_name || ''}
                  </td>
                  <td className="px-4 py-3 text-sm text-orange-600 font-medium">
                    {lead.client_name || '\u2014'}
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-500">
                    {lead.phone_masked || '\u2014'}
                  </td>
                  <td className="px-4 py-3 text-sm capitalize text-gray-500">
                    {(lead.source || '').replace('_', ' ')}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium capitalize px-2 py-0.5 rounded-md border ${stateBadge(lead.state)}`}>
                      {(lead.state || '').replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-12 rounded-full h-1.5 bg-gray-100">
                        <div
                          className={`h-1.5 rounded-full ${scoreBarColor(lead.score || 0)}`}
                          style={{ width: `${lead.score || 0}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-gray-400">{lead.score ?? '\u2014'}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {lead.first_response_ms ? (
                      <span className={`text-xs font-mono font-medium flex items-center gap-1 ${responseTimeColor(lead.first_response_ms)}`}>
                        <Clock className="w-3 h-3" />
                        {(lead.first_response_ms / 1000).toFixed(1)}s
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">{'\u2014'}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-400">
                    {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '\u2014'}
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
