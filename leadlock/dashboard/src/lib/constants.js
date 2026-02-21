/**
 * Shared constants — single source of truth for auth keys,
 * thresholds, poll intervals, tab definitions, and pagination defaults.
 */

// ── Auth localStorage keys ──
export const AUTH_KEYS = {
  TOKEN: 'll_token',
  BUSINESS: 'll_business',
  IS_ADMIN: 'll_is_admin',
  CLIENT_ID: 'll_client_id',
};

// ── Response-time thresholds (ms) ──
export const RESPONSE_TIME = {
  EXCELLENT: 10_000,  // <= 10s  → green
  GOOD: 30_000,       // <= 30s  → orange
  ACCEPTABLE: 60_000, // <= 60s  → amber
  // > 60s              → red
};

// ── Auto-refresh poll intervals (ms) ──
export const POLL_INTERVALS = {
  DASHBOARD: 30_000,
  LEAD_FEED: 15_000,
  CONVERSATIONS: 10_000,
};

// ── Lead state filter tabs ──
export const LEAD_STATE_TABS = [
  { id: 'all', label: 'All' },
  { id: 'new', label: 'New' },
  { id: 'qualifying', label: 'Qualifying' },
  { id: 'qualified', label: 'Qualified' },
  { id: 'booked', label: 'Booked' },
  { id: 'cold', label: 'Cold' },
  { id: 'opted_out', label: 'Opted Out' },
];

// ── Pagination defaults ──
export const PER_PAGE = {
  LEADS: 20,
  ADMIN_LEADS: 25,
  CONVERSATIONS: 50,
};
