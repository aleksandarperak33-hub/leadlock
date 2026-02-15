import { ArrowUp, ArrowDown } from 'lucide-react';

export default function MetricCard({ title, value, subtitle, trend, trendLabel, icon: Icon, color = 'brand' }) {
  const colorMap = {
    brand: 'bg-brand-500/10 text-brand-400',
    green: 'bg-emerald-500/10 text-emerald-400',
    yellow: 'bg-amber-500/10 text-amber-400',
    red: 'bg-red-500/10 text-red-400',
    purple: 'bg-purple-500/10 text-purple-400',
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-400 font-medium">{title}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
        </div>
        {Icon && (
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${colorMap[color]}`}>
            <Icon className="w-5 h-5" />
          </div>
        )}
      </div>
      {trend !== undefined && (
        <div className="flex items-center gap-1.5 mt-3">
          {trend >= 0 ? (
            <ArrowUp className="w-3.5 h-3.5 text-emerald-400" />
          ) : (
            <ArrowDown className="w-3.5 h-3.5 text-red-400" />
          )}
          <span className={`text-xs font-medium ${trend >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {Math.abs(trend)}%
          </span>
          {trendLabel && <span className="text-xs text-slate-500">{trendLabel}</span>}
        </div>
      )}
    </div>
  );
}
