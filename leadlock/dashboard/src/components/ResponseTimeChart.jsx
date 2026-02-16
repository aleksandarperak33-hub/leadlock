import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid } from 'recharts';

const BUCKET_COLORS = {
  '0-10s': '#10b981',
  '10-30s': '#6366f1',
  '30-60s': '#f59e0b',
  '60s+': '#ef4444',
};

const TOOLTIP_STYLE = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
  color: '#111827',
  fontSize: '12px',
  boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
  padding: '8px 12px',
};

export default function ResponseTimeChart({ data = [] }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wider mb-4 text-gray-500">
        Response Time Distribution
      </h3>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
            <XAxis
              dataKey="bucket"
              tick={{ fill: '#9ca3af', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#9ca3af', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              cursor={{ fill: '#f9fafb' }}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={BUCKET_COLORS[entry.bucket] || '#6366f1'} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
