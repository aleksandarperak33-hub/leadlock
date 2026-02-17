import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  CartesianGrid,
} from 'recharts';
import { BarChart3 } from 'lucide-react';
import EmptyState from './ui/EmptyState';

/**
 * Color mapping for response time buckets.
 */
const BUCKET_COLORS = {
  '0-10s': '#10b981',
  '10-30s': '#fb923c',
  '30-60s': '#f59e0b',
  '60s+': '#ef4444',
};

const TOOLTIP_STYLE = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: '12px',
  color: '#111827',
  fontSize: '12px',
  boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
  padding: '10px 14px',
};

/**
 * ResponseTimeChart -- Bar chart showing response time distribution.
 * Parent wraps in a card container; this component renders only the chart.
 *
 * @param {Array} data - Array of { bucket, count } objects
 */
export default function ResponseTimeChart({ data = [] }) {
  if (data.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No response time data"
        description="Response time distribution will appear here once leads are received."
      />
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
        <CartesianGrid stroke="#f3f4f6" vertical={false} strokeDasharray="3 3" />
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
            <Cell
              key={i}
              fill={BUCKET_COLORS[entry.bucket] || '#f97316'}
              fillOpacity={0.9}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
