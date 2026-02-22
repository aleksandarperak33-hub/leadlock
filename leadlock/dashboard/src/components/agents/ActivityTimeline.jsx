import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import Badge from '../ui/Badge';

const DEFAULT_LIMIT = 50;
const LOAD_MORE_INCREMENT = 50;

const STATUS_VARIANT = {
  completed: 'success',
  failed: 'danger',
  pending: 'neutral',
  processing: 'info',
};

const DOT_COLOR = {
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
 * Groups an array of tasks by their calendar date string.
 */
function groupByDate(tasks) {
  const groups = {};
  for (const task of tasks) {
    const date = new Date(task.created_at).toLocaleDateString();
    if (!groups[date]) groups[date] = [];
    groups[date].push(task);
  }
  return groups;
}

/**
 * Returns "Today", "Yesterday", or a formatted date label.
 */
function formatDateLabel(dateString) {
  const date = new Date(dateString);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (date.toLocaleDateString() === today.toLocaleDateString()) return 'Today';
  if (date.toLocaleDateString() === yesterday.toLocaleDateString()) return 'Yesterday';

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
 * Builds a lookup map from agent name to agent object for efficient color/name resolution.
 */
function buildAgentLookup(agents) {
  const lookup = {};
  for (const agent of agents) {
    lookup[agent.name] = agent;
  }
  return lookup;
}

/**
 * Vertical timeline feed showing recent agent actions grouped by date.
 * @param {{ agents: Array<object> }} props
 */
export default function ActivityTimeline({ agents }) {
  const [tasks, setTasks] = useState([]);
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function fetchTasks() {
      try {
        const result = await api.getAgentTasks({ per_page: limit });
        if (!cancelled) {
          setTasks(result.data?.tasks || []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load activity');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchTasks();
    return () => { cancelled = true; };
  }, [limit, retryCount]);

  const agentLookup = buildAgentLookup(agents || []);
  const grouped = groupByDate(tasks);
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

  if (tasks.length === 0) {
    return (
      <p className="text-sm text-gray-400 text-center py-8">No recent activity</p>
    );
  }

  return (
    <div className="space-y-6">
      {dateKeys.map((dateKey) => {
        const firstTask = grouped[dateKey][0];
        const label = formatDateLabel(firstTask.created_at);

        return (
          <div key={dateKey}>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              {label}
            </h4>
            <div className="relative pl-5">
              {/* Vertical connecting line */}
              <div className="absolute left-[4.5px] top-1 bottom-1 w-px bg-gray-200" />

              <div className="space-y-3">
                {grouped[dateKey].map((task, idx) => {
                  const agent = agentLookup[task.agent] || {};
                  const dotClass = DOT_COLOR[agent.color] || 'bg-gray-400';

                  return (
                    <div key={task.id || idx} className="relative flex items-start gap-3">
                      {/* Colored dot */}
                      <div className={`absolute -left-5 top-1.5 w-2.5 h-2.5 rounded-full ring-2 ring-white ${dotClass}`} />

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-gray-900">
                            {agent.display_name || task.agent}
                          </span>
                          <span className="text-sm text-gray-500">{task.task_type}</span>
                          <Badge variant={STATUS_VARIANT[task.status] || 'neutral'} size="sm">
                            {task.status}
                          </Badge>
                          <span className="text-xs text-gray-400 ml-auto whitespace-nowrap">
                            {formatRelativeTime(task.created_at)}
                          </span>
                        </div>
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
