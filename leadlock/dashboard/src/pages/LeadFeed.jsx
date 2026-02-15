import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import LeadStatusBadge from '../components/LeadStatusBadge';
import { Search, Filter, Clock, ChevronLeft, ChevronRight } from 'lucide-react';

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
    if (!ms) return 'text-slate-500';
    if (ms < 10000) return 'text-emerald-400';
    if (ms < 60000) return 'text-amber-400';
    return 'text-red-400';
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Leads</h1>
        <span className="text-sm text-slate-400">{total} total</span>
      </div>

      {/* Search and filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search name, phone, service..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full pl-10 pr-4 py-2.5 bg-slate-900 border border-slate-800 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500"
          />
        </div>
      </div>

      {/* State filter chips */}
      <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
        {STATE_FILTERS.map(s => (
          <button
            key={s}
            onClick={() => { setStateFilter(s); setPage(1); }}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-colors ${
              stateFilter === s
                ? 'bg-brand-600/20 text-brand-400 border border-brand-500/30'
                : 'bg-slate-900 text-slate-400 border border-slate-800 hover:border-slate-700'
            }`}
          >
            {s === 'all' ? 'All' : s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Name</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Phone</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Source</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Status</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Score</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Service</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Response</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Time</th>
              </tr>
            </thead>
            <tbody>
              {loading && leads.length === 0 ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} className="border-b border-slate-800/50">
                    <td colSpan={8} className="px-4 py-4">
                      <div className="h-4 bg-slate-800 rounded animate-pulse" />
                    </td>
                  </tr>
                ))
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                    No leads found
                  </td>
                </tr>
              ) : leads.map(lead => (
                <tr
                  key={lead.id}
                  onClick={() => navigate(`/conversations/${lead.id}`)}
                  className="border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 text-sm text-white font-medium">
                    {lead.first_name || 'Unknown'} {lead.last_name || ''}
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-400">{lead.phone_masked}</td>
                  <td className="px-4 py-3 text-xs text-slate-400 capitalize">{lead.source?.replace('_', ' ')}</td>
                  <td className="px-4 py-3"><LeadStatusBadge status={lead.state} /></td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-12 bg-slate-800 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${lead.score >= 70 ? 'bg-emerald-500' : lead.score >= 40 ? 'bg-amber-500' : 'bg-red-500'}`}
                          style={{ width: `${lead.score}%` }}
                        />
                      </div>
                      <span className="text-xs text-slate-400">{lead.score}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400 max-w-[120px] truncate">{lead.service_type || '\u2014'}</td>
                  <td className="px-4 py-3">
                    {lead.first_response_ms ? (
                      <span className={`text-xs font-medium flex items-center gap-1 ${responseTimeColor(lead.first_response_ms)}`}>
                        <Clock className="w-3 h-3" />
                        {(lead.first_response_ms / 1000).toFixed(1)}s
                      </span>
                    ) : (
                      <span className="text-xs text-slate-500">\u2014</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {new Date(lead.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800">
            <span className="text-xs text-slate-500">Page {page} of {pages}</span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-800 disabled:opacity-30"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage(p => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-800 disabled:opacity-30"
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
