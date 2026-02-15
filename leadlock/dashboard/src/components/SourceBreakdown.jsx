const SOURCE_LABELS = {
  google_lsa: 'Google LSA',
  angi: 'Angi',
  facebook: 'Facebook',
  website: 'Website',
  missed_call: 'Missed Call',
  text_in: 'Text-In',
  thumbtack: 'Thumbtack',
  referral: 'Referral',
  yelp: 'Yelp',
};

const SOURCE_COLORS = {
  google_lsa: 'bg-blue-500',
  angi: 'bg-orange-500',
  facebook: 'bg-indigo-500',
  website: 'bg-emerald-500',
  missed_call: 'bg-amber-500',
  text_in: 'bg-cyan-500',
  thumbtack: 'bg-green-500',
  referral: 'bg-purple-500',
  yelp: 'bg-red-500',
};

export default function SourceBreakdown({ data = {} }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, v]) => v), 1);

  if (!entries.length) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-sm font-medium text-slate-400 mb-4">Leads by Source</h3>
        <p className="text-slate-500 text-sm">No data available</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <h3 className="text-sm font-medium text-slate-400 mb-4">Leads by Source</h3>
      <div className="space-y-3">
        {entries.map(([source, count]) => (
          <div key={source}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-slate-300">{SOURCE_LABELS[source] || source}</span>
              <span className="text-slate-400 font-medium">{count}</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-500 ${SOURCE_COLORS[source] || 'bg-slate-500'}`}
                style={{ width: `${(count / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
