import { ArrowUp, ArrowDown } from 'lucide-react';

const ACCENT_COLORS = {
  brand: { color: '#6366f1', glow: 'rgba(99, 102, 241, 0.12)' },
  green: { color: '#10b981', glow: 'rgba(16, 185, 129, 0.12)' },
  yellow: { color: '#f59e0b', glow: 'rgba(245, 158, 11, 0.12)' },
  red: { color: '#ef4444', glow: 'rgba(239, 68, 68, 0.12)' },
  purple: { color: '#a855f7', glow: 'rgba(168, 85, 247, 0.12)' },
};

export default function MetricCard({ title, value, subtitle, trend, trendLabel, icon: Icon, color = 'brand' }) {
  const accent = ACCENT_COLORS[color] || ACCENT_COLORS.brand;

  return (
    <div className="glass-card gradient-border relative overflow-hidden p-5 group">
      {/* Ambient glow on hover */}
      <div className="absolute -top-12 -right-12 w-24 h-24 rounded-full transition-opacity duration-500 opacity-0 group-hover:opacity-100" style={{
        background: `radial-gradient(circle, ${accent.glow}, transparent 70%)`,
      }} />

      {/* Left accent bar */}
      <div
        className="absolute left-0 top-4 bottom-4 w-[2px] rounded-full"
        style={{ background: `linear-gradient(180deg, ${accent.color}, transparent)`, opacity: 0.5 }}
      />

      <div className="pl-3 relative">
        <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
          {title}
        </p>
        <p className="text-[26px] font-bold tracking-tight mt-1.5 font-mono" style={{ color: 'var(--text-primary)' }}>
          {value}
        </p>
        {subtitle && (
          <p className="text-[11px] mt-1.5" style={{ color: 'var(--text-tertiary)' }}>{subtitle}</p>
        )}
        {trend !== undefined && (
          <div className="flex items-center gap-1.5 mt-2.5">
            <div className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-md" style={{
              background: trend >= 0 ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
            }}>
              {trend >= 0 ? (
                <ArrowUp className="w-3 h-3" style={{ color: '#10b981' }} />
              ) : (
                <ArrowDown className="w-3 h-3" style={{ color: '#ef4444' }} />
              )}
              <span className="text-[11px] font-semibold" style={{ color: trend >= 0 ? '#10b981' : '#ef4444' }}>
                {Math.abs(trend)}%
              </span>
            </div>
            {trendLabel && (
              <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{trendLabel}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
