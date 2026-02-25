import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { LEAD_STATE_TABS, POLL_INTERVALS, PER_PAGE } from '../lib/constants';
import { responseTimeClass } from '../lib/response-time';
import { useDebounce } from '../hooks/useDebounce';
import PageHeader from '../components/ui/PageHeader';
import SearchInput from '../components/ui/SearchInput';
import Tabs from '../components/ui/Tabs';
import DataTable from '../components/ui/DataTable';
import LeadStatusBadge from '../components/LeadStatusBadge';
import Pagination from '../components/ui/Pagination';
import { Clock } from 'lucide-react';

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
          className={`text-xs font-mono font-medium flex items-center gap-1 ${responseTimeClass(val)}`}
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
 * Fetches leads with auto-refresh.
 */
export default function LeadFeed() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [stateFilter, setStateFilter] = useState('all');
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 300);
  const [loading, setLoading] = useState(true);

  const fetchLeads = async () => {
    try {
      const params = { page, per_page: PER_PAGE.LEADS };
      if (stateFilter !== 'all') params.state = stateFilter;
      if (debouncedSearch) params.search = debouncedSearch;

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
    const interval = setInterval(fetchLeads, POLL_INTERVALS.LEAD_FEED);
    return () => clearInterval(interval);
  }, [page, stateFilter, debouncedSearch]);

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
      <span className="text-xs font-mono text-gray-400 bg-gray-50 border border-gray-200/50 px-2.5 py-1 rounded-lg">
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
        tabs={LEAD_STATE_TABS}
        activeId={stateFilter}
        onChange={handleFilterChange}
      />

      {loading && leads.length === 0 ? (
        <div className="bg-white border border-gray-200/50 rounded-2xl shadow-card overflow-hidden">
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

      <Pagination page={page} pages={pages} onChange={setPage} />
    </div>
  );
}
