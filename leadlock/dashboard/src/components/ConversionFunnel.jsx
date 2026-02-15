export default function ConversionFunnel({ data = {} }) {
  const stages = [
    { key: 'new', label: 'New Leads', color: 'bg-blue-500' },
    { key: 'qualifying', label: 'Qualifying', color: 'bg-amber-500' },
    { key: 'qualified', label: 'Qualified', color: 'bg-orange-500' },
    { key: 'booked', label: 'Booked', color: 'bg-emerald-500' },
  ];

  const maxCount = Math.max(...stages.map(s => data[s.key] || 0), 1);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <h3 className="text-sm font-medium text-slate-400 mb-4">Conversion Funnel</h3>
      <div className="space-y-3">
        {stages.map(({ key, label, color }) => {
          const count = data[key] || 0;
          return (
            <div key={key}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-slate-300">{label}</span>
                <span className="text-slate-400 font-medium">{count}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-3">
                <div
                  className={`h-3 rounded-full transition-all duration-500 ${color}`}
                  style={{ width: `${(count / maxCount) * 100}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
