const STATUS_CONFIG = {
  new:         { label: 'New',         color: '#5a72f0' },
  intake_sent: { label: 'Intake Sent', color: '#38bdf8' },
  qualifying:  { label: 'Qualifying',  color: '#fbbf24' },
  qualified:   { label: 'Qualified',   color: '#fb923c' },
  booking:     { label: 'Booking',     color: '#a78bfa' },
  booked:      { label: 'Booked',      color: '#34d399' },
  completed:   { label: 'Completed',   color: '#4ade80' },
  cold:        { label: 'Cold',        color: '#64748b' },
  dead:        { label: 'Dead',        color: '#475569' },
  opted_out:   { label: 'Opted Out',   color: '#f87171' },
};

export default function LeadStatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.new;

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-[3px] rounded-md text-[11px] font-medium"
      style={{
        background: `${config.color}12`,
        color: config.color,
        border: `1px solid ${config.color}20`,
      }}
    >
      <span
        className="w-1 h-1 rounded-full"
        style={{ background: config.color }}
      />
      {config.label}
    </span>
  );
}
