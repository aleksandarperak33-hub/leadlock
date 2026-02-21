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
import { BUCKET_COLORS, CHART_COLORS, TOOLTIP_STYLE, BRAND } from '../lib/colors';

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
        <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} strokeDasharray="3 3" />
        <XAxis
          dataKey="bucket"
          tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
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
              fill={BUCKET_COLORS[entry.bucket] || BRAND[500]}
              fillOpacity={0.9}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
