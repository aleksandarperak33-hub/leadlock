const STAGE_COLORS = {
  new: '#6366f1',
  qualifying: '#fbbf24',
  qualified: '#fb923c',
  booked: '#34d399',
};

export default function ConversionFunnel({ data = {} }) {
  const stages = [
    { key: 'new', label: 'New Leads' },
    { key: 'qualifying', label: 'Qualifying' },
    { key: 'qualified', label: 'Qualified' },
    { key: 'booked', label: 'Booked' },
  ];

  const maxCount = Math.max(...stages.map(s => data[s.key] || 0), 1);

  return (
    <div className="glass-card gradient-border p-5">
      <h3 className="text-[11px] font-medium uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>
        Conversion Funnel
      </h3>
      <div className="space-y-3">
        {stages.map(({ key, label }) => {
          const count = data[key] || 0;
          const color = STAGE_COLORS[key];
          return (
            <div key={key}>
              <div className="flex items-center justify-between text-[12px] mb-1.5">
                <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{count}</span>
              </div>
              <div className="w-full rounded-full h-2" style={{ background: 'var(--surface-3)' }}>
                <div
                  className="h-2 rounded-full transition-all duration-700"
                  style={{ width: `${(count / maxCount) * 100}%`, background: color, opacity: 0.75 }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
