import { AUTH_KEYS } from '../lib/constants';

const API_BASE = '/api/v1/dashboard';
const ADMIN_BASE = '/api/v1/admin';
const SALES_BASE = '/api/v1/sales';

const REQUEST_TIMEOUT_MS = 10_000;

/**
 * Clears all auth state from localStorage and redirects to login.
 */
function clearSession() {
  Object.values(AUTH_KEYS).forEach((key) => localStorage.removeItem(key));
  window.location.href = '/login';
}

/**
 * Factory that creates a request function for a given base URL.
 * Handles auth headers, 401 auto-logout, 403 errors, timeout, and JSON parsing.
 */
function createRequest(basePath) {
  return async function request(path, options = {}) {
    const token = localStorage.getItem(AUTH_KEYS.TOKEN);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const res = await fetch(`${basePath}${path}`, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...options.headers,
        },
      });

      if (res.status === 401) {
        console.warn('API returned 401, clearing session');
        clearSession();
        throw new Error('Unauthorized');
      }

      if (res.status === 403) {
        throw new Error('Admin access required');
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      return res.json();
    } finally {
      clearTimeout(timeoutId);
    }
  };
}

const ANALYTICS_BASE = '/api/v1/analytics';
const AGENTS_BASE = '/api/v1/agents';

const request = createRequest(API_BASE);
const adminRequest = createRequest(ADMIN_BASE);
const salesRequest = createRequest(SALES_BASE);
const analyticsRequest = createRequest(ANALYTICS_BASE);
const agentsRequest = createRequest(AGENTS_BASE);

export const api = {
  login: (email, password) =>
    fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }).then(r => {
      if (!r.ok) throw new Error('Invalid credentials');
      return r.json();
    }),

  getMetrics: (period = '7d') => request(`/metrics?period=${period}`),
  getROI: (period = '30d') => request(`/roi?period=${period}`),

  getLeads: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/leads?${qs}`);
  },
  getLead: (id) => request(`/leads/${id}`),
  getConversations: (leadId) => request(`/leads/${leadId}/conversations`),

  getActivity: (limit = 50) => request(`/activity?limit=${limit}`),

  getWeeklyReport: (week) => request(`/reports/weekly${week ? `?week=${week}` : ''}`),

  getSettings: () => request('/settings'),
  updateSettings: (data) => request('/settings', { method: 'PUT', body: JSON.stringify(data) }),

  getComplianceSummary: () => request('/compliance/summary'),

  // Lead actions
  updateLeadStatus: (id, status) => request(`/leads/${id}/status`, { method: 'PUT', body: JSON.stringify({ status }) }),
  archiveLead: (id, archived) => request(`/leads/${id}/archive`, { method: 'PUT', body: JSON.stringify({ archived }) }),
  updateLeadTags: (id, tags) => request(`/leads/${id}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),
  updateLeadNotes: (id, notes) => request(`/leads/${id}/notes`, { method: 'PUT', body: JSON.stringify({ notes }) }),

  // Reply to lead conversation
  sendReply: (leadId, message) => request(`/leads/${leadId}/reply`, { method: 'POST', body: JSON.stringify({ message }) }),

  // Bookings
  getBookings: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/bookings?${qs}`);
  },

  // Reports
  getCustomReport: (start, end) => request(`/reports/custom?start=${start}&end=${end}`),
  exportLeadsCSV: () => {
    const token = localStorage.getItem(AUTH_KEYS.TOKEN);
    return fetch(`${API_BASE}/leads/export?format=csv`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then(r => {
      if (!r.ok) throw new Error('Export failed');
      return r.blob();
    });
  },

  // Compliance
  getComplianceDetails: (type) => request(`/compliance/details?type=${type}`),

  // Admin endpoints
  getAdminOverview: () => adminRequest('/overview'),
  getAdminClients: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return adminRequest(`/clients?${qs}`);
  },
  getAdminClient: (id) => adminRequest(`/clients/${id}`),
  getAdminLeads: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return adminRequest(`/leads?${qs}`);
  },
  getAdminRevenue: (period = '30d') => adminRequest(`/revenue?period=${period}`),
  getAdminHealth: () => adminRequest('/health'),
  getAdminOutreach: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return adminRequest(`/outreach?${qs}`);
  },
  createOutreach: (data) => adminRequest('/outreach', { method: 'POST', body: JSON.stringify(data) }),
  updateOutreach: (id, data) => adminRequest(`/outreach/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteOutreach: (id) => adminRequest(`/outreach/${id}`, { method: 'DELETE' }),
  convertOutreach: (id) => adminRequest(`/outreach/${id}/convert`, { method: 'POST' }),
  createAdminClient: (data) => adminRequest('/clients', { method: 'POST', body: JSON.stringify(data) }),

  // Sales Engine
  getSalesConfig: () => salesRequest('/config'),
  updateSalesConfig: (data) => salesRequest('/config', { method: 'PUT', body: JSON.stringify(data) }),
  getSalesMetrics: (period = '30d') => salesRequest(`/metrics?period=${period}`),
  getScrapeJobs: (page = 1) => salesRequest(`/scrape-jobs?page=${page}`),
  triggerScrapeJob: (data) => salesRequest('/scrape-jobs', { method: 'POST', body: JSON.stringify(data) }),

  // Prospects
  getProspects: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return salesRequest(`/prospects?${qs}`);
  },
  getProspect: (id) => salesRequest(`/prospects/${id}`),
  updateProspect: (id, data) => salesRequest(`/prospects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProspect: (id) => salesRequest(`/prospects/${id}`, { method: 'DELETE' }),
  createProspect: (data) => salesRequest('/prospects', { method: 'POST', body: JSON.stringify(data) }),
  blacklistProspect: (id) => salesRequest(`/prospects/${id}/blacklist`, { method: 'POST' }),
  getProspectEmails: (id) => salesRequest(`/prospects/${id}/emails`),

  // Worker status & controls
  getWorkerStatus: () => salesRequest('/worker-status'),
  pauseWorker: (name) => salesRequest(`/workers/${name}/pause`, { method: 'POST' }),
  resumeWorker: (name) => salesRequest(`/workers/${name}/resume`, { method: 'POST' }),

  // Campaigns
  getCampaigns: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return salesRequest(`/campaigns?${qs}`);
  },
  getCampaign: (id) => salesRequest(`/campaigns/${id}`),
  createCampaign: (data) => salesRequest('/campaigns', { method: 'POST', body: JSON.stringify(data) }),
  updateCampaign: (id, data) => salesRequest(`/campaigns/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  pauseCampaign: (id) => salesRequest(`/campaigns/${id}/pause`, { method: 'POST' }),
  resumeCampaign: (id) => salesRequest(`/campaigns/${id}/resume`, { method: 'POST' }),

  // Campaign Detail
  getCampaignDetail: (id) => salesRequest(`/campaigns/${id}/detail`),
  getCampaignProspects: (id, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return salesRequest(`/campaigns/${id}/prospects?${qs}`);
  },
  activateCampaign: (id) => salesRequest(`/campaigns/${id}/activate`, { method: 'POST' }),
  assignProspects: (id, data) => salesRequest(`/campaigns/${id}/assign-prospects`, { method: 'POST', body: JSON.stringify(data) }),
  getCampaignMetrics: (id) => salesRequest(`/campaigns/${id}/metrics`),

  // Inbox
  getInbox: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return salesRequest(`/inbox?${qs}`);
  },
  getInboxThread: (id) => salesRequest(`/inbox/${id}/thread`),

  // Templates
  getTemplates: () => salesRequest('/templates'),
  createTemplate: (data) => salesRequest('/templates', { method: 'POST', body: JSON.stringify(data) }),
  updateTemplate: (id, data) => salesRequest(`/templates/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTemplate: (id) => salesRequest(`/templates/${id}`, { method: 'DELETE' }),

  // Command Center
  getCommandCenter: () => salesRequest('/command-center'),

  // Insights
  getInsights: () => salesRequest('/insights'),

  // Bulk operations
  bulkUpdateProspects: (data) => salesRequest('/prospects/bulk', { method: 'POST', body: JSON.stringify(data) }),

  // Analytics
  getAnalyticsFunnel: (trade) => analyticsRequest(`/funnel${trade ? `?trade=${trade}` : ''}`),
  getAnalyticsCostPerLead: (trade) => analyticsRequest(`/cost-per-lead${trade ? `?trade=${trade}` : ''}`),
  getAnalyticsEmailPerf: () => analyticsRequest('/email-performance'),
  getAnalyticsAbTests: () => analyticsRequest('/ab-tests'),
  getAnalyticsPipeline: () => analyticsRequest('/pipeline'),
  getAnalyticsAgentCosts: (days = 7) => analyticsRequest(`/agent-costs?days=${days}`),

  // Agent Fleet
  getAgentFleet: () => agentsRequest('/fleet'),
  getAgentActivity: (name, limit = 20) => agentsRequest(`/${name}/activity?limit=${limit}`),
  getAgentTasks: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return agentsRequest(`/tasks?${qs}`);
  },
  getAgentCosts: (period = '7d') => agentsRequest(`/costs?period=${period}`),
  getSystemMap: () => agentsRequest('/system-map'),
  getActivityFeed: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return agentsRequest(`/activity-feed?${qs}`);
  },
};
