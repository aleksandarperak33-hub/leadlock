import { ArrowUp, ArrowDown } from 'lucide-react';

const ACCENT_COLORS = {
  brand: '#5a72f0',
  green: '#34d399',
  yellow: '#fbbf24',
  red: '#f87171',
  purple: '#a78bfa',
};

export default function MetricCard({ title, value, subtitle, trend, trendLabel, icon: Icon, color = 'brand' }) {
  const accent = ACCENT_COLORS[color] || ACCENT_COLORS.brand;

  return (
    <div
      className="relative overflow-hidden rounded-card p-4 transition-all duration-200"
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border)',
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border-active)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
    >
      {/* Left accent bar */}
      <div
        className="absolute left-0 top-3 bottom-3 w-[2px] rounded-full"
        style={{ background: accent, opacity: 0.6 }}
      />

      <div className="pl-2.5">
        <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
          {title}
        </p>
        <p className="text-2xl font-semibold tracking-tight mt-1 font-mono" style={{ color: 'var(--text-primary)' }}>
          {value}
        </p>
        {subtitle && (
          <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{subtitle}</p>
        )}
        {trend !== undefined && (
          <div className="flex items-center gap-1 mt-2">
            {trend >= 0 ? (
              <ArrowUp className="w-3 h-3" style={{ color: '#34d399' }} />
            ) : (
              <ArrowDown className="w-3 h-3" style={{ color: '#f87171' }} />
            )}
            <span className="text-[11px] font-medium" style={{ color: trend >= 0 ? '#34d399' : '#f87171' }}>
              {Math.abs(trend)}%
            </span>
            {trendLabel && (
              <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{trendLabel}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
