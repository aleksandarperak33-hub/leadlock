import { useState, useEffect, useRef } from 'react';
import { api } from '../../api/client';
import Badge from '../ui/Badge';

const DEFAULT_LIMIT = 50;
const LOAD_MORE_INCREMENT = 50;
const POLL_INTERVAL_MS = 30_000;

const STATUS_VARIANT = {
  success: 'success',
  failure: 'danger',
  failed: 'danger',
  error: 'danger',
  skipped: 'neutral',
  completed: 'success',
  pending: 'neutral',
  processing: 'info',
};

const DOT_COLOR = {
  purple: 'bg-purple-500', blue: 'bg-blue-500', amber: 'bg-amber-500',
  green: 'bg-green-500', cyan: 'bg-cyan-500', red: 'bg-red-500',
  pink: 'bg-pink-500', indigo: 'bg-indigo-500', emerald: 'bg-emerald-500',
  sky: 'bg-sky-500', lime: 'bg-lime-500', orange: 'bg-orange-500',
  stone: 'bg-stone-500', violet: 'bg-violet-500', gray: 'bg-gray-500',
};

/**
 * Groups an array of events by ISO date key (YYYY-MM-DD).
 * Uses ISO substring instead of toLocaleDateString to avoid locale-dependent keys.
 */
function groupByDate(events) {
  const groups = {};
  for (const event of events) {
    const date = event.created_at ? event.created_at.slice(0, 10) : 'unknown';
    if (!groups[date]) groups[date] = [];
    groups[date].push(event);
  }
  return groups;
}

/**
 * Returns "Today", "Yesterday", or a formatted date label from ISO date key.
 */
function formatDateLabel(isoDateKey) {
  const date = new Date(isoDateKey + 'T00:00:00');
  const today = new Date();
  const todayKey = today.toISOString().slice(0, 10);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayKey = yesterday.toISOString().slice(0, 10);

  if (isoDateKey === todayKey) return 'Today';
  if (isoDateKey === yesterdayKey) return 'Yesterday';

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * Formats a timestamp into relative time (e.g. "2m ago").
 */
function formatRelativeTime(timestamp) {
  if (!timestamp) return '';
  const seconds = (Date.now() - new Date(timestamp).getTime()) / 1000;
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

/**
 * Formats a cost value for display.
 */
function formatCost(cost) {
  if (cost == null || cost === 0) return null;
  return `$${Number(cost).toFixed(4)}`;
}

/**
 * Vertical timeline feed showing real agent activity from EventLog.
 */
export default function ActivityTimeline() {
  const [events, setEvents] = useState([]);
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);
  const intervalRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchEvents() {
      try {
        const result = await api.getActivityFeed({ limit: String(limit) });
        if (!cancelled) {
          setEvents(result.data?.events || []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load activity');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchEvents();

    // Auto-refresh every 30s
    intervalRef.current = setInterval(fetchEvents, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(intervalRef.current);
    };
  }, [limit, retryCount]);

  const grouped = groupByDate(events);
  const dateKeys = Object.keys(grouped);

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-gray-200" />
            <div className="h-4 bg-gray-100 rounded-lg flex-1" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card p-6 text-center">
        <p className="text-red-600 text-sm mb-2">{error}</p>
        <button onClick={() => setRetryCount((n) => n + 1)} className="text-sm text-orange-600 hover:underline">Retry</button>
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <p className="text-sm text-gray-400 text-center py-8">No recent activity</p>
    );
  }

  return (
    <div className="space-y-6">
      {dateKeys.map((dateKey) => {
        const label = formatDateLabel(dateKey);

        return (
          <div key={dateKey}>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              {label}
            </h4>
            <div className="relative pl-5">
              {/* Vertical connecting line */}
              <div className="absolute left-[4.5px] top-1 bottom-1 w-px bg-gray-200" />

              <div className="space-y-3">
                {grouped[dateKey].map((event, idx) => {
                  const dotClass = DOT_COLOR[event.agent_color] || 'bg-gray-400';
                  const costStr = formatCost(event.cost_usd);

                  return (
                    <div key={event.id || idx} className="relative flex items-start gap-3">
                      {/* Colored dot */}
                      <div className={`absolute -left-5 top-1.5 w-2.5 h-2.5 rounded-full ring-2 ring-white ${dotClass}`} />

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-gray-900">
                            {event.agent_display_name}
                          </span>
                          <span className="text-sm text-gray-500">{event.action}</span>
                          <Badge variant={STATUS_VARIANT[event.status] || 'neutral'} size="sm">
                            {event.status}
                          </Badge>
                          {costStr && (
                            <span className="text-[11px] font-mono text-gray-400">{costStr}</span>
                          )}
                          <span className="text-xs text-gray-400 ml-auto whitespace-nowrap">
                            {formatRelativeTime(event.created_at)}
                          </span>
                        </div>
                        {event.message && (
                          <p className="text-xs text-gray-500 mt-0.5 truncate">{event.message}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}

      {/* Load more button */}
      <div className="text-center pt-2">
        <button
          type="button"
          onClick={() => setLimit((prev) => prev + LOAD_MORE_INCREMENT)}
          className="text-sm text-orange-500 hover:text-orange-600 font-medium cursor-pointer transition-colors"
        >
          Load more
        </button>
      </div>
    </div>
  );
}
