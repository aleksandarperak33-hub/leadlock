import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import LeadStatusBadge from '../components/LeadStatusBadge';
import { Search, Clock, ChevronLeft, ChevronRight } from 'lucide-react';

const STATE_FILTERS = ['all', 'new', 'qualifying', 'qualified', 'booked', 'cold', 'opted_out'];

const FILTER_LABELS = {
  all: 'All',
  new: 'New',
  qualifying: 'Qualifying',
  qualified: 'Qualified',
  booked: 'Booked',
  cold: 'Cold',
  opted_out: 'Opted Out',
};

const responseTimeColor = (ms) => {
  if (!ms) return 'text-gray-400';
  if (ms < 10000) return 'text-emerald-600';
  if (ms < 60000) return 'text-amber-600';
  return 'text-red-600';
};

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

  return (
    <div className="animate-page-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold tracking-tight text-gray-900">
          Leads
        </h1>
        <span className="text-xs font-mono tabular-nums text-gray-400 bg-gray-100 px-2.5 py-1 rounded-lg">
          {total} total
        </span>
      </div>

      {/* Search */}
      <div className="mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search name, phone, service..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 placeholder-gray-400 outline-none transition-all focus:border-orange-500 focus:ring-2 focus:ring-orange-100"
          />
        </div>
      </div>

      {/* Filter chips */}
      <div className="flex gap-2 mb-5 overflow-x-auto pb-1">
        {STATE_FILTERS.map(s => {
          const isActive = stateFilter === s;
          return (
            <button
              key={s}
              onClick={() => { setStateFilter(s); setPage(1); }}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all cursor-pointer ${
                isActive
                  ? 'bg-orange-50 text-orange-700 border border-orange-200'
                  : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300 hover:text-gray-700'
              }`}
            >
              {FILTER_LABELS[s]}
            </button>
          );
        })}
      </div>

      {/* Table card */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden card-accent-top">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {['Name', 'Phone', 'Source', 'Status', 'Score', 'Service', 'Response', 'Date'].map(h => (
                  <th
                    key={h}
                    className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && leads.length === 0 ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    <td colSpan={8} className="px-4 py-4">
                      <div className="h-4 bg-gray-100 rounded-lg animate-pulse" />
                    </td>
                  </tr>
                ))
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-16 text-center text-sm text-gray-400">
                    No leads found
                  </td>
                </tr>
              ) : leads.map(lead => (
                <tr
                  key={lead.id}
                  onClick={() => navigate(`/conversations/${lead.id}`)}
                  className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors"
                >
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {lead.first_name || 'Unknown'} {lead.last_name || ''}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-500">
                    {lead.phone_masked}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 capitalize">
                    {lead.source?.replace('_', ' ')}
                  </td>
                  <td className="px-4 py-3">
                    <LeadStatusBadge status={lead.state} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-10 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${lead.score}%`,
                            background: lead.score >= 70 ? '#10b981' : lead.score >= 40 ? '#f59e0b' : '#ef4444',
                          }}
                        />
                      </div>
                      <span className="text-[11px] font-mono text-gray-500">
                        {lead.score}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 max-w-[120px] truncate">
                    {lead.service_type || '\u2014'}
                  </td>
                  <td className="px-4 py-3">
                    {lead.first_response_ms ? (
                      <span className={`text-[11px] font-mono font-medium flex items-center gap-1 ${responseTimeColor(lead.first_response_ms)}`}>
                        <Clock className="w-3 h-3" />
                        {(lead.first_response_ms / 1000).toFixed(1)}s
                      </span>
                    ) : (
                      <span className="text-[11px] text-gray-400">{'\u2014'}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[11px] font-mono text-gray-400">
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
            <span className="text-xs font-mono text-gray-400">
              Page {page} of {pages}
            </span>
            <div className="flex gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage(p => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed"
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
