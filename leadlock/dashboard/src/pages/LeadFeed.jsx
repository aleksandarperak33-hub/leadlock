import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import SearchInput from '../components/ui/SearchInput';
import Tabs from '../components/ui/Tabs';
import DataTable from '../components/ui/DataTable';
import LeadStatusBadge from '../components/LeadStatusBadge';
import { Clock, ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Filter tab definitions for lead states.
 */
const STATE_TABS = [
  { id: 'all', label: 'All' },
  { id: 'new', label: 'New' },
  { id: 'qualifying', label: 'Qualifying' },
  { id: 'qualified', label: 'Qualified' },
  { id: 'booked', label: 'Booked' },
  { id: 'cold', label: 'Cold' },
  { id: 'opted_out', label: 'Opted Out' },
];

/**
 * Returns a Tailwind text color class for response time values.
 */
const responseTimeColor = (ms) => {
  if (!ms) return 'text-gray-400';
  if (ms < 10000) return 'text-emerald-600';
  if (ms < 60000) return 'text-amber-600';
  return 'text-red-600';
};

/**
 * Column definitions for the leads DataTable.
 */
const getColumns = () => [
  {
    key: 'name',
    label: 'Name',
    render: (_val, row) => (
      <span className="text-sm font-medium text-gray-900">
        {row.first_name || 'Unknown'} {row.last_name || ''}
      </span>
    ),
  },
  {
    key: 'phone_masked',
    label: 'Phone',
    render: (val) => (
      <span className="text-xs font-mono text-gray-500">{val}</span>
    ),
  },
  {
    key: 'source',
    label: 'Source',
    render: (val) => (
      <span className="text-xs text-gray-500 capitalize">
        {val?.replaceAll('_', ' ')}
      </span>
    ),
  },
  {
    key: 'state',
    label: 'Status',
    render: (val) => <LeadStatusBadge status={val} />,
  },
  {
    key: 'score',
    label: 'Score',
    render: (val) => {
      if (val == null) return <span className="text-xs text-gray-400">{'\u2014'}</span>;
      return (
        <div className="flex items-center gap-2">
          <div className="w-12 h-1.5 rounded-full bg-gray-100 overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{
                width: `${val}%`,
                background:
                  val >= 70 ? '#10b981' : val >= 40 ? '#f59e0b' : '#ef4444',
              }}
            />
          </div>
          <span className="text-xs font-mono text-gray-500">{val}</span>
        </div>
      );
    },
  },
  {
    key: 'first_response_ms',
    label: 'Response',
    render: (val) =>
      val ? (
        <span
          className={`text-xs font-mono font-medium flex items-center gap-1 ${responseTimeColor(val)}`}
        >
          <Clock className="w-3 h-3" />
          {(val / 1000).toFixed(1)}s
        </span>
      ) : (
        <span className="text-xs text-gray-400">{'\u2014'}</span>
      ),
  },
  {
    key: 'created_at',
    label: 'Date',
    render: (val) => (
      <span className="text-xs font-mono text-gray-400">
        {val ? new Date(val).toLocaleDateString() : '\u2014'}
      </span>
    ),
  },
];

/**
 * LeadFeed -- Searchable, filterable table of all leads with pagination.
 * Fetches leads with 15-second auto-refresh.
 */
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

  const handleSearch = (val) => {
    setSearch(val);
    setPage(1);
  };

  const handleFilterChange = (tabId) => {
    setStateFilter(tabId);
    setPage(1);
  };

  const headerActions = (
    <div className="flex items-center gap-3">
      <span className="text-xs font-mono text-gray-400 bg-gray-50 border border-gray-200/60 px-2.5 py-1 rounded-lg">
        {total} total
      </span>
      <div className="w-64">
        <SearchInput
          value={search}
          onChange={handleSearch}
          placeholder="Search name, phone, service..."
        />
      </div>
    </div>
  );

  return (
    <div className="space-y-0">
      <PageHeader title="Leads" actions={headerActions} />

      <Tabs
        tabs={STATE_TABS}
        activeId={stateFilter}
        onChange={handleFilterChange}
      />

      {loading && leads.length === 0 ? (
        <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm overflow-hidden">
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className="px-4 py-4 border-b border-gray-100 last:border-0"
            >
              <div className="h-4 bg-gray-100 rounded-lg animate-pulse" />
            </div>
          ))}
        </div>
      ) : (
        <DataTable
          columns={getColumns()}
          data={leads}
          emptyMessage="No leads found"
          onRowClick={(row) => navigate(`/conversations/${row.id}`)}
        />
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-sm font-mono text-gray-400">
            Page {page} of {pages}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {(() => {
              const startPage = Math.max(1, Math.min(page - 2, pages - 4));
              const endPage = Math.min(pages, startPage + 4);
              const pageNumbers = Array.from({ length: endPage - startPage + 1 }, (_, i) => startPage + i);
              return pageNumbers.map((pageNum) => (
                <button
                  key={pageNum}
                  onClick={() => setPage(pageNum)}
                  className={`w-8 h-8 rounded-lg text-sm font-medium cursor-pointer transition-colors ${
                    page === pageNum
                      ? 'bg-orange-500 text-white'
                      : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                  }`}
                >
                  {pageNum}
                </button>
              ));
            })()}
            <button
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
              disabled={page === pages}
              className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
