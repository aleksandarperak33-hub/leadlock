export default function LiveIndicator({ label = 'System Active' }) {
  return (
    <div className="flex items-center gap-2">
      <span className="relative flex h-2 w-2">
        <span
          className="animate-glow-ring absolute inline-flex h-full w-full rounded-full"
          style={{ background: '#34d399' }}
        />
        <span
          className="relative inline-flex rounded-full h-2 w-2 animate-live-pulse"
          style={{ background: '#34d399' }}
        />
      </span>
      <span className="text-[11px] font-medium" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
    </div>
  );
}
