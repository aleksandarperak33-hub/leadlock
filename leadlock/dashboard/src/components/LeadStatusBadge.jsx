const STATUS_CONFIG = {
  new: { label: 'New', bg: 'bg-blue-500/10', text: 'text-blue-400', dot: 'bg-blue-400' },
  intake_sent: { label: 'Intake Sent', bg: 'bg-sky-500/10', text: 'text-sky-400', dot: 'bg-sky-400' },
  qualifying: { label: 'Qualifying', bg: 'bg-amber-500/10', text: 'text-amber-400', dot: 'bg-amber-400' },
  qualified: { label: 'Qualified', bg: 'bg-orange-500/10', text: 'text-orange-400', dot: 'bg-orange-400' },
  booking: { label: 'Booking', bg: 'bg-purple-500/10', text: 'text-purple-400', dot: 'bg-purple-400' },
  booked: { label: 'Booked', bg: 'bg-emerald-500/10', text: 'text-emerald-400', dot: 'bg-emerald-400' },
  completed: { label: 'Completed', bg: 'bg-green-500/10', text: 'text-green-400', dot: 'bg-green-400' },
  cold: { label: 'Cold', bg: 'bg-slate-500/10', text: 'text-slate-400', dot: 'bg-slate-400' },
  dead: { label: 'Dead', bg: 'bg-slate-600/10', text: 'text-slate-500', dot: 'bg-slate-500' },
  opted_out: { label: 'Opted Out', bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-400' },
};

export default function LeadStatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.new;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${config.dot}`} />
      {config.label}
    </span>
  );
}
