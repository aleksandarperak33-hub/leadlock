import { ArrowUp, ArrowDown, Minus } from 'lucide-react';

/**
 * Color configuration mapping for icon badges, accent lines, and delta indicators.
 */
const COLOR_MAP = {
  brand: {
    badge: 'bg-orange-50 text-orange-600',
    accent: 'bg-orange-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-500',
  },
  green: {
    badge: 'bg-emerald-50 text-emerald-600',
    accent: 'bg-emerald-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-500',
  },
  yellow: {
    badge: 'bg-amber-50 text-amber-600',
    accent: 'bg-amber-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-500',
  },
  red: {
    badge: 'bg-red-50 text-red-600',
    accent: 'bg-red-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-500',
  },
  blue: {
    badge: 'bg-blue-50 text-blue-600',
    accent: 'bg-blue-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-500',
  },
  purple: {
    badge: 'bg-purple-50 text-purple-600',
    accent: 'bg-purple-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-500',
  },
};

/**
 * StatCard - Premium metric display card with accent line, icon badge, and delta indicator.
 *
 * @param {string} label - Uppercase label above the metric value
 * @param {string|number} value - The primary metric value to display
 * @param {number} [delta] - Percentage change (positive = up, negative = down)
 * @param {string} [deltaLabel] - Text label next to the delta percentage
 * @param {import('lucide-react').LucideIcon} [icon] - Lucide icon component for the badge
 * @param {string} [color='brand'] - Color variant: brand | green | yellow | red | blue | purple
 */
export default function StatCard({
  label,
  value,
  delta,
  deltaLabel,
  icon: Icon,
  color = 'brand',
}) {
  const colors = COLOR_MAP[color] || COLOR_MAP.brand;
  const isPositive = delta !== undefined && delta > 0;
  const isNegative = delta !== undefined && delta < 0;
  const DeltaArrow = isPositive ? ArrowUp : isNegative ? ArrowDown : Minus;
  const deltaColor = isPositive
    ? colors.deltaUp
    : isNegative
      ? colors.deltaDown
      : 'text-gray-400';

  return (
    <div className="bg-white border border-gray-200/50 rounded-2xl p-5 shadow-card relative overflow-hidden group transition-shadow duration-200 hover:shadow-card-hover">
      {/* Subtle top accent line */}
      <div className={`absolute top-0 left-0 right-0 h-[2px] ${colors.accent} opacity-60`} />

      <div className="flex items-start justify-between">
        <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-widest">
          {label}
        </p>
        {Icon && (
          <div
            className={`w-9 h-9 rounded-xl flex items-center justify-center ${colors.badge}`}
          >
            <Icon className="w-[18px] h-[18px]" strokeWidth={1.75} />
          </div>
        )}
      </div>

      <p className="metric-value text-metric text-gray-900 mt-3">
        {value}
      </p>

      {delta !== undefined && (
        <div className="flex items-center gap-1.5 mt-3">
          <div className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md ${
            isPositive ? 'bg-emerald-50' : isNegative ? 'bg-red-50' : 'bg-gray-50'
          }`}>
            <DeltaArrow className={`w-3 h-3 ${deltaColor}`} strokeWidth={2.5} />
            <span className={`text-xs font-semibold ${deltaColor}`}>
              {Math.abs(delta)}%
            </span>
          </div>
          {deltaLabel && (
            <span className="text-[11px] text-gray-400 font-medium">{deltaLabel}</span>
          )}
        </div>
      )}
      {delta === undefined && deltaLabel && (
        <div className="mt-3">
          <span className="text-[11px] text-gray-400 font-medium">{deltaLabel}</span>
        </div>
      )}
    </div>
  );
}
