const API_BASE = '/api/v1/dashboard';
const ADMIN_BASE = '/api/v1/admin';
const SALES_BASE = '/api/v1/sales';

async function request(path, options = {}) {
  const token = localStorage.getItem('ll_token');
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (res.status === 401) {
    localStorage.removeItem('ll_token');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

async function adminRequest(path, options = {}) {
  const token = localStorage.getItem('ll_token');
  const res = await fetch(`${ADMIN_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (res.status === 401) {
    localStorage.removeItem('ll_token');
    window.location.href = '/login';
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
}

async function salesRequest(path, options = {}) {
  const token = localStorage.getItem('ll_token');
  const res = await fetch(`${SALES_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (res.status === 401) {
    localStorage.removeItem('ll_token');
    window.location.href = '/login';
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
}

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

  // Lead actions (Phase 2)
  updateLeadStatus: (id, status) => request(`/leads/${id}/status`, { method: 'PUT', body: JSON.stringify({ status }) }),
  archiveLead: (id, archived) => request(`/leads/${id}/archive`, { method: 'PUT', body: JSON.stringify({ archived }) }),
  updateLeadTags: (id, tags) => request(`/leads/${id}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),
  updateLeadNotes: (id, notes) => request(`/leads/${id}/notes`, { method: 'PUT', body: JSON.stringify({ notes }) }),

  // Bookings (Phase 2)
  getBookings: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/bookings?${qs}`);
  },

  // Reports (Phase 2)
  getCustomReport: (start, end) => request(`/reports/custom?start=${start}&end=${end}`),
  exportLeadsCSV: () => {
    const token = localStorage.getItem('ll_token');
    return fetch(`${API_BASE}/leads/export?format=csv`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then(r => {
      if (!r.ok) throw new Error('Export failed');
      return r.blob();
    });
  },

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

  // Campaigns (Phase 3)
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

  // Templates (Phase 3)
  getTemplates: () => salesRequest('/templates'),
  createTemplate: (data) => salesRequest('/templates', { method: 'POST', body: JSON.stringify(data) }),
  updateTemplate: (id, data) => salesRequest(`/templates/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTemplate: (id) => salesRequest(`/templates/${id}`, { method: 'DELETE' }),

  // Command Center (Phase 5)
  getCommandCenter: () => salesRequest('/command-center'),

  // Insights (Phase 3)
  getInsights: () => salesRequest('/insights'),

  // Bulk operations (Phase 3)
  bulkUpdateProspects: (data) => salesRequest('/prospects/bulk', { method: 'POST', body: JSON.stringify(data) }),
};
