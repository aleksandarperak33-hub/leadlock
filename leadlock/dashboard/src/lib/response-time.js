/**
 * Shared response-time formatting utilities.
 * Replaces 4 separate implementations across LeadCard, LeadFeed, Dashboard, AdminLeads.
 */
import { RESPONSE_TIME } from './constants';

/**
 * Returns a Tailwind text-color class for a response time in milliseconds.
 * @param {number|null} ms - Response time in milliseconds
 * @returns {string} Tailwind class name
 */
export function responseTimeClass(ms) {
  if (!ms) return 'text-gray-400';
  if (ms <= RESPONSE_TIME.EXCELLENT) return 'text-emerald-600';
  if (ms <= RESPONSE_TIME.GOOD) return 'text-orange-500';
  if (ms <= RESPONSE_TIME.ACCEPTABLE) return 'text-amber-600';
  return 'text-red-600';
}

/**
 * Returns a hex color string for a response time in milliseconds.
 * Useful for inline styles (e.g. in chart data).
 * @param {number|null} ms - Response time in milliseconds
 * @returns {string} Hex color string
 */
export function responseTimeHex(ms) {
  if (!ms) return '#9ca3af';       // gray-400
  if (ms <= RESPONSE_TIME.EXCELLENT) return '#34d399'; // emerald-400
  if (ms <= RESPONSE_TIME.GOOD) return '#f97316';      // orange-500
  if (ms <= RESPONSE_TIME.ACCEPTABLE) return '#fbbf24'; // amber-400
  return '#f87171';                // red-400
}

/**
 * Returns a semantic color name for a response time value.
 * Useful for components that accept a `color` prop (e.g. StatCard).
 * @param {number|null} ms - Response time in milliseconds
 * @returns {'brand'|'green'|'yellow'|'red'} Semantic color name
 */
export function responseTimeColor(ms) {
  if (!ms) return 'brand';
  if (ms <= RESPONSE_TIME.EXCELLENT) return 'green';
  if (ms <= RESPONSE_TIME.ACCEPTABLE) return 'yellow';
  return 'red';
}
