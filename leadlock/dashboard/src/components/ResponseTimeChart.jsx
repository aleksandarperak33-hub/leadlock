import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const BUCKET_COLORS = {
  '0-10s': '#34d399',
  '10-30s': '#5a72f0',
  '30-60s': '#fbbf24',
  '60s+': '#f87171',
};

export default function ResponseTimeChart({ data = [] }) {
  return (
    <div className="rounded-card p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      <h3 className="text-[11px] font-medium uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>
        Response Time Distribution
      </h3>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
            <XAxis
              dataKey="bucket"
              tick={{ fill: '#5a6178', fontSize: 11, fontFamily: 'var(--font-mono, monospace)' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#5a6178', fontSize: 11, fontFamily: 'var(--font-mono, monospace)' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: '#161820',
                border: '1px solid rgba(148, 163, 184, 0.1)',
                borderRadius: '8px',
                color: '#e8eaed',
                fontSize: '12px',
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              }}
              cursor={{ fill: 'rgba(255,255,255,0.02)' }}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={BUCKET_COLORS[entry.bucket] || '#5a72f0'} fillOpacity={0.8} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
