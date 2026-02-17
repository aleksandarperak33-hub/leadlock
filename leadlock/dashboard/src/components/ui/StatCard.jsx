import { ArrowUp, ArrowDown, Minus } from 'lucide-react';

/**
 * Color configuration mapping for icon badges and delta indicators.
 */
const COLOR_MAP = {
  brand: {
    badge: 'bg-orange-50 text-orange-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-600',
  },
  green: {
    badge: 'bg-emerald-50 text-emerald-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-600',
  },
  yellow: {
    badge: 'bg-amber-50 text-amber-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-600',
  },
  red: {
    badge: 'bg-red-50 text-red-500',
    deltaUp: 'text-emerald-600',
    deltaDown: 'text-red-600',
  },
};

/**
 * StatCard — Metric display card with optional delta indicator and icon badge.
 *
 * @param {string} label - Uppercase label above the metric value
 * @param {string} value - The primary metric value to display
 * @param {number} [delta] - Percentage change (positive = up, negative = down)
 * @param {string} [deltaLabel] - Text label next to the delta percentage
 * @param {import('lucide-react').LucideIcon} [icon] - Lucide icon component for the badge
 * @param {string} [color='brand'] - Color variant: brand | green | yellow | red
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
  const isNeutral = delta !== undefined && delta === 0;
  const DeltaArrow = isPositive ? ArrowUp : isNegative ? ArrowDown : Minus;
  const deltaColor = isPositive
    ? colors.deltaUp
    : isNegative
      ? colors.deltaDown
      : 'text-gray-400';

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm relative">
      {Icon && (
        <div
          className={`absolute top-5 right-5 w-10 h-10 rounded-xl flex items-center justify-center ${colors.badge}`}
        >
          <Icon className="w-5 h-5" />
        </div>
      )}

      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
        {label}
      </p>

      <p className="text-3xl font-bold text-gray-900 font-mono mt-2">
        {value}
      </p>

      {delta !== undefined && (
        <div className="flex items-center gap-1 mt-3">
          <DeltaArrow className={`w-3 h-3 ${deltaColor}`} />
          <span className={`text-xs font-semibold ${deltaColor}`}>
            {Math.abs(delta)}%
          </span>
          {deltaLabel && (
            <span className="text-xs text-gray-400">{deltaLabel}</span>
          )}
        </div>
      )}
      {delta === undefined && deltaLabel && (
        <div className="mt-3">
          <span className="text-xs text-gray-400">{deltaLabel}</span>
        </div>
      )}
    </div>
  );
}
