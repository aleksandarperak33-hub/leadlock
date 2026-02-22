import { Activity, Pause, AlertTriangle, DollarSign, ListTodo, PowerOff } from 'lucide-react';

const ITEMS = [
  { key: 'running', label: 'Active', icon: Activity, color: 'emerald', getValue: (s) => s.healthy },
  { key: 'idle', label: 'Idle', icon: Pause, color: 'gray', getValue: (s) => s.warning },
  { key: 'error', label: 'Error', icon: AlertTriangle, color: 'red', getValue: (s) => s.unhealthy },
  { key: 'disabled', label: 'Disabled', icon: PowerOff, color: 'slate', getValue: (s) => s.disabled ?? 0 },
  { key: 'cost', label: 'Today', icon: DollarSign, color: 'blue', getValue: (s) => `$${s.total_cost_today?.toFixed(3) ?? '0.000'}` },
  { key: 'tasks', label: 'Today', icon: ListTodo, color: 'orange', getValue: (s) => `${s.total_tasks_today ?? 0} Tasks` },
];

const DOT_COLORS = {
  emerald: 'bg-emerald-500',
  gray: 'bg-gray-400',
  red: 'bg-red-500',
  blue: 'bg-blue-500',
  orange: 'bg-orange-500',
  slate: 'bg-slate-400',
};

const BG_COLORS = {
  emerald: 'bg-emerald-50',
  gray: 'bg-gray-50',
  red: 'bg-red-50',
  blue: 'bg-blue-50',
  orange: 'bg-orange-50',
  slate: 'bg-slate-50',
};

const ICON_COLORS = {
  emerald: 'text-emerald-500',
  gray: 'text-gray-400',
  red: 'text-red-500',
  blue: 'text-blue-500',
  orange: 'text-orange-500',
  slate: 'text-slate-400',
};

/**
 * Fleet-level KPI strip with 5 metric tiles.
 * @param {{ summary: object }} props
 */
export default function FleetSummaryBar({ summary }) {
  if (!summary) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 animate-fade-up">
      {ITEMS.map(({ key, label, icon: Icon, color, getValue }) => (
        <div key={key} className="glass-card p-3.5 flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg ${BG_COLORS[color]} flex items-center justify-center shrink-0`}>
            <Icon className={`w-4 h-4 ${ICON_COLORS[color]}`} />
          </div>
          <div>
            <div className="text-lg font-semibold text-gray-900 leading-tight">
              {getValue(summary)}
            </div>
            <div className="text-xs text-gray-500">{label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
