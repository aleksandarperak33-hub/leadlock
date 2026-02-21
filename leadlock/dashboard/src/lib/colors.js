/**
 * Centralized color constants for charts and branded UI elements.
 * Use these wherever Tailwind classes can't reach (e.g. Recharts props, inline SVG).
 */

export const BRAND = {
  500: '#f97316',
  600: '#ea580c',
};

export const CHART_COLORS = {
  stroke: {
    primary: '#f97316',
    secondary: '#10b981',
    tertiary: '#3b82f6',
  },
  grid: '#f3f4f6',
  axis: '#9ca3af',
  cursor: '#e5e7eb',
  gradientStart: '#f97316',
};

export const SEMANTIC = {
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#3b82f6',
};

export const TOOLTIP_STYLE = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: '12px',
  color: '#111827',
  fontSize: '12px',
  boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
  padding: '10px 14px',
};

/** Response time bucket colors. */
export const BUCKET_COLORS = {
  '0-10s': '#10b981',
  '10-30s': '#fb923c',
  '30-60s': '#f59e0b',
  '60s+': '#ef4444',
};

/** Orange palette for source breakdown bars. */
export const SOURCE_BAR_PALETTE = [
  '#f97316',
  '#fb923c',
  '#fdba74',
  '#fed7aa',
  '#ffedd5',
  '#f97316',
  '#fb923c',
  '#fdba74',
  '#fed7aa',
];
