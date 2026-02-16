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
  google_lsa: '#6366f1',
  angi: '#f59e0b',
  facebook: '#8b5cf6',
  website: '#10b981',
  missed_call: '#f59e0b',
  text_in: '#06b6d4',
  thumbtack: '#22c55e',
  referral: '#a78bfa',
  yelp: '#ef4444',
};

export default function SourceBreakdown({ data = {} }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);

  if (!entries.length) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider mb-4 text-gray-500">
          Leads by Source
        </h3>
        <p className="text-sm text-gray-400">No data available</p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wider mb-4 text-gray-500">
        Leads by Source
      </h3>
      <div className="space-y-3">
        {entries.map(([source, count]) => {
          const pct = total > 0 ? ((count / total) * 100).toFixed(0) : 0;
          const barColor = SOURCE_COLORS[source] || '#6366f1';
          return (
            <div key={source}>
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="text-gray-600">{SOURCE_LABELS[source] || source}</span>
                <div className="flex items-center gap-2">
                  <span className="tabular-nums text-gray-400">{pct}%</span>
                  <span className="tabular-nums font-medium text-gray-900">{count}</span>
                </div>
              </div>
              <div className="w-full rounded-full h-1.5 bg-gray-100">
                <div
                  className="h-1.5 rounded-full transition-all duration-700"
                  style={{
                    width: `${(count / max) * 100}%`,
                    background: barColor,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
