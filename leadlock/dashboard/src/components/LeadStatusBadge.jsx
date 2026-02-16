const STATUS_CONFIG = {
  new:         { label: 'New',         color: '#6366f1', glow: 'rgba(99, 102, 241, 0.10)' },
  intake_sent: { label: 'Intake Sent', color: '#38bdf8', glow: 'rgba(56, 189, 248, 0.10)' },
  qualifying:  { label: 'Qualifying',  color: '#fbbf24', glow: 'rgba(251, 191, 36, 0.10)' },
  qualified:   { label: 'Qualified',   color: '#fb923c', glow: 'rgba(251, 146, 60, 0.10)' },
  booking:     { label: 'Booking',     color: '#a78bfa', glow: 'rgba(167, 139, 250, 0.10)' },
  booked:      { label: 'Booked',      color: '#34d399', glow: 'rgba(52, 211, 153, 0.10)' },
  completed:   { label: 'Completed',   color: '#4ade80', glow: 'rgba(74, 222, 128, 0.10)' },
  cold:        { label: 'Cold',        color: '#64748b', glow: 'rgba(100, 116, 139, 0.10)' },
  dead:        { label: 'Dead',        color: '#475569', glow: 'rgba(71, 85, 105, 0.10)' },
  opted_out:   { label: 'Opted Out',   color: '#f87171', glow: 'rgba(248, 113, 113, 0.10)' },
};

export default function LeadStatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.new;

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-[3px] rounded-md text-[11px] font-medium"
      style={{
        background: config.glow,
        color: config.color,
        border: `1px solid ${config.color}20`,
        boxShadow: `0 0 8px ${config.glow}`,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: config.color, boxShadow: `0 0 6px ${config.color}` }}
      />
      {config.label}
    </span>
  );
}
