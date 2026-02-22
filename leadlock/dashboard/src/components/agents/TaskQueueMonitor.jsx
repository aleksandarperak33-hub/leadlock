import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../../api/client';
import DataTable from '../ui/DataTable';
import Pagination from '../ui/Pagination';
import Badge from '../ui/Badge';

const AUTO_REFRESH_MS = 10_000;
const PER_PAGE = 20;

const STATUS_FILTERS = [
  { key: '', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'processing', label: 'Processing' },
  { key: 'completed', label: 'Completed' },
  { key: 'failed', label: 'Failed' },
];

const STATUS_VARIANT = {
  completed: 'success',
  failed: 'danger',
  pending: 'neutral',
  processing: 'info',
};

const AGENT_DOT_COLOR = {
  purple: 'bg-purple-500',
  blue: 'bg-blue-500',
  amber: 'bg-amber-500',
  green: 'bg-green-500',
  cyan: 'bg-cyan-500',
  red: 'bg-red-500',
  pink: 'bg-pink-500',
  indigo: 'bg-indigo-500',
  emerald: 'bg-emerald-500',
};

/**
 * Formats a timestamp into a relative time string (e.g. "2m ago", "1h ago").
 */
function formatRelativeTime(timestamp) {
  if (!timestamp) return '--';
  const seconds = (Date.now() - new Date(timestamp).getTime()) / 1000;
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

/**
 * Formats duration in seconds to a display string, or returns a dash if null.
 */
function formatDuration(durationS) {
  if (durationS == null) return '--';
  return `${durationS.toFixed(1)}s`;
}

/**
 * Truncates a string to the specified length, appending ellipsis if needed.
 */
function truncate(str, maxLen = 40) {
  if (!str) return '--';
  return str.length > maxLen ? `${str.slice(0, maxLen)}...` : str;
}

/**
 * Full-width task queue table with status filters, auto-refresh, and pagination.
 */
export default function TaskQueueMonitor() {
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ tasks: [], pagination: { total: 0, total_pages: 1 }, status_counts: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchTasks = useCallback(async (opts = {}) => {
    const currentStatus = opts.status ?? status;
    const currentPage = opts.page ?? page;
    try {
      const params = { per_page: PER_PAGE, page: currentPage };
      if (currentStatus) {
        params.status = currentStatus;
      }
      const result = await api.getAgentTasks(params);
      setData(result.data);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, [status, page]);

  useEffect(() => {
    setLoading(true);
    fetchTasks();

    intervalRef.current = setInterval(() => fetchTasks(), AUTO_REFRESH_MS);
    return () => clearInterval(intervalRef.current);
  }, [fetchTasks]);

  const handleStatusChange = (nextStatus) => {
    setStatus(nextStatus);
    setPage(1);
  };

  const totalPages = data.pagination?.total_pages ?? 1;

  const columns = [
    { key: 'task_type', label: 'Type', render: (val) => (
      <span className="font-mono text-xs">{val}</span>
    )},
    { key: 'agent', label: 'Agent', render: (val) => (
      <span className="text-sm text-gray-700">{val || '--'}</span>
    )},
    { key: 'status', label: 'Status', render: (val) => (
      <Badge variant={STATUS_VARIANT[val] || 'neutral'} size="sm">
        {val?.charAt(0).toUpperCase() + val?.slice(1)}
      </Badge>
    )},
    { key: 'priority', label: 'Priority', align: 'right', render: (val) => (
      <span className="font-mono text-xs">{val ?? '--'}</span>
    )},
    { key: 'created_at', label: 'Created', render: (val) => (
      <span className="text-xs text-gray-500">{formatRelativeTime(val)}</span>
    )},
    { key: 'duration_s', label: 'Duration', align: 'right', render: (val) => (
      <span className="font-mono text-xs">{formatDuration(val)}</span>
    )},
    { key: 'retry_count', label: 'Retries', align: 'right', render: (val) => (
      <span className="font-mono text-xs">{val ?? 0}</span>
    )},
    { key: 'error_message', label: 'Error', render: (val) => (
      <span className="text-xs text-red-500" title={val || undefined}>
        {truncate(val)}
      </span>
    )},
  ];

  return (
    <div className="space-y-4">
      {/* Error banner */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Status tab filters */}
      <div className="flex items-center gap-1 bg-gray-50/80 rounded-xl p-1 w-fit">
        {STATUS_FILTERS.map((filter) => {
          const isActive = status === filter.key;
          const count = filter.key
            ? (data.status_counts?.[filter.key] ?? 0)
            : (data.pagination?.total ?? 0);

          return (
            <button
              key={filter.key}
              type="button"
              onClick={() => handleStatusChange(filter.key)}
              className={`
                px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer
                inline-flex items-center gap-1.5
                ${isActive
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
                }
              `}
            >
              {filter.label}
              <span className={`
                text-xs font-mono px-1.5 py-0.5 rounded-md
                ${isActive ? 'bg-orange-50 text-orange-600' : 'bg-gray-100 text-gray-400'}
              `}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Task table */}
      <DataTable
        columns={columns}
        data={data.tasks || []}
        emptyMessage="No tasks found"
        loading={loading}
        loadingRows={5}
      />

      {/* Pagination */}
      <Pagination page={page} pages={totalPages} onChange={setPage} />
    </div>
  );
}
