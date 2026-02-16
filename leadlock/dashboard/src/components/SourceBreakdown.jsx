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
  google_lsa: '#5a72f0',
  angi: '#f59e0b',
  facebook: '#818cf8',
  website: '#34d399',
  missed_call: '#fbbf24',
  text_in: '#22d3ee',
  thumbtack: '#4ade80',
  referral: '#a78bfa',
  yelp: '#f87171',
};

export default function SourceBreakdown({ data = {} }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);

  if (!entries.length) {
    return (
      <div className="glass-card gradient-border p-5">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>
          Leads by Source
        </h3>
        <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>No data available</p>
      </div>
    );
  }

  return (
    <div className="glass-card gradient-border p-5">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>
        Leads by Source
      </h3>
      <div className="space-y-3">
        {entries.map(([source, count]) => {
          const pct = total > 0 ? ((count / total) * 100).toFixed(0) : 0;
          return (
            <div key={source}>
              <div className="flex items-center justify-between text-[12px] mb-1.5">
                <span style={{ color: 'var(--text-secondary)' }}>{SOURCE_LABELS[source] || source}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{pct}%</span>
                  <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{count}</span>
                </div>
              </div>
              <div className="w-full rounded-full h-[5px]" style={{ background: 'var(--surface-3)' }}>
                <div
                  className="h-[5px] rounded-full transition-all duration-700"
                  style={{
                    width: `${(count / max) * 100}%`,
                    background: SOURCE_COLORS[source] || '#5a72f0',
                    opacity: 0.75,
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
