import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { Clock, ChevronLeft, ChevronRight } from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import SearchInput from '../../components/ui/SearchInput';
import Tabs from '../../components/ui/Tabs';
import DataTable from '../../components/ui/DataTable';
import Badge from '../../components/ui/Badge';

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
 * Maps a lead state to a Badge variant.
 */
const stateVariant = (state) => {
  switch (state) {
    case 'booked':
    case 'completed':
      return 'success';
    case 'qualified':
    case 'qualifying':
      return 'info';
    case 'new':
    case 'intake_sent':
      return 'warning';
    case 'cold':
    case 'dead':
    case 'opted_out':
      return 'danger';
    default:
      return 'neutral';
  }
};

/**
 * Returns the color class for a response time in milliseconds.
 * <=10s emerald, <=30s orange, <=60s amber, >60s red.
 */
const responseTimeColor = (ms) => {
  if (!ms) return 'text-gray-400';
  if (ms <= 10000) return 'text-emerald-600';
  if (ms <= 30000) return 'text-orange-500';
  if (ms <= 60000) return 'text-amber-600';
  return 'text-red-600';
};

const TABLE_COLUMNS = [
  {
    key: 'name',
    label: 'Name',
    render: (_val, row) => (
      <span className="font-medium text-gray-900">
        {row.first_name || 'Unknown'} {row.last_name || ''}
      </span>
    ),
  },
  {
    key: 'client_name',
    label: 'Client',
    render: (val) => (
      <span className="text-gray-600">{val || '\u2014'}</span>
    ),
  },
  {
    key: 'phone_masked',
    label: 'Phone',
    render: (val) => (
      <span className="font-mono text-gray-500">{val || '\u2014'}</span>
    ),
  },
  {
    key: 'source',
    label: 'Source',
    render: (val) => (
      <span className="capitalize text-gray-600">
        {(val || '').replace('_', ' ') || '\u2014'}
      </span>
    ),
  },
  {
    key: 'state',
    label: 'Status',
    render: (val) => (
      <Badge variant={stateVariant(val)} size="sm">
        {(val || '').replace('_', ' ')}
      </Badge>
    ),
  },
  {
    key: 'score',
    label: 'Score',
    align: 'right',
    render: (val) => (
      <span className="font-mono text-gray-600">{val ?? '\u2014'}</span>
    ),
  },
  {
    key: 'first_response_ms',
    label: 'Response',
    render: (val) => {
      if (!val) return <span className="text-xs text-gray-400">{'\u2014'}</span>;
      return (
        <span className={`text-xs font-mono font-medium flex items-center gap-1 ${responseTimeColor(val)}`}>
          <Clock className="w-3 h-3" />
          {(val / 1000).toFixed(1)}s
        </span>
      );
    },
  },
  {
    key: 'created_at',
    label: 'Date',
    render: (val) => (
      <span className="font-mono text-xs text-gray-400">
        {val ? new Date(val).toLocaleDateString() : '\u2014'}
      </span>
    ),
  },
];

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

  const handleSearchChange = (val) => {
    setSearch(val);
    setPage(1);
  };

  const handleTabChange = (tabId) => {
    setStateFilter(tabId);
    setPage(1);
  };

  return (
    <div className="bg-[#FAFAFA] min-h-screen">
      <PageHeader
        title="All Leads"
        subtitle={`${total} total`}
        actions={
          <div className="w-72">
            <SearchInput
              value={search}
              onChange={handleSearchChange}
              placeholder="Search name, phone, client..."
            />
          </div>
        }
      />

      {/* State Tabs */}
      <Tabs
        tabs={STATE_TABS}
        activeId={stateFilter}
        onChange={handleTabChange}
      />

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
          data={leads}
          emptyMessage="No leads found"
        />
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-xs font-mono text-gray-400">
            Page {page} of {pages}
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
