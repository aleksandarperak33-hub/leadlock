import { ArrowUp, ArrowDown } from 'lucide-react';

const ACCENT_COLORS = {
  brand: { bg: 'bg-indigo-50', text: 'text-indigo-600', border: 'border-indigo-100', icon: 'text-indigo-500' },
  green: { bg: 'bg-emerald-50', text: 'text-emerald-600', border: 'border-emerald-100', icon: 'text-emerald-500' },
  yellow: { bg: 'bg-amber-50', text: 'text-amber-600', border: 'border-amber-100', icon: 'text-amber-500' },
  red: { bg: 'bg-red-50', text: 'text-red-600', border: 'border-red-100', icon: 'text-red-500' },
  purple: { bg: 'bg-purple-50', text: 'text-purple-600', border: 'border-purple-100', icon: 'text-purple-500' },
};

export default function MetricCard({ title, value, subtitle, trend, trendLabel, icon: Icon, color = 'brand' }) {
  const accent = ACCENT_COLORS[color] || ACCENT_COLORS.brand;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 relative overflow-hidden card-hover-lift card-accent-top">
      {/* Icon badge */}
      {Icon && (
        <div className={`absolute top-4 right-4 w-9 h-9 rounded-xl ${accent.bg} ${accent.border} border flex items-center justify-center`}>
          <Icon className={`w-[18px] h-[18px] ${accent.icon}`} strokeWidth={1.75} />
        </div>
      )}

      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
          {title}
        </p>
        <p className="text-[28px] font-bold tracking-tight mt-1 text-gray-900 tabular-nums leading-none">
          {value}
        </p>
        {subtitle && (
          <p className="text-xs mt-2 text-gray-400">{subtitle}</p>
        )}
        {trend !== undefined && (
          <div className="flex items-center gap-1.5 mt-3">
            <div className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md ${
              trend >= 0 ? 'bg-emerald-50 border border-emerald-100' : 'bg-red-50 border border-red-100'
            }`}>
              {trend >= 0 ? (
                <ArrowUp className="w-3 h-3 text-emerald-600" />
              ) : (
                <ArrowDown className="w-3 h-3 text-red-600" />
              )}
              <span className={`text-[11px] font-bold ${trend >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                {Math.abs(trend)}%
              </span>
            </div>
            {trendLabel && (
              <span className="text-[11px] text-gray-400">{trendLabel}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
