const API_BASE = '/api/v1/dashboard';
const ADMIN_BASE = '/api/v1/admin';

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
  getAdminOutreach: () => adminRequest('/outreach'),
  createOutreach: (data) => adminRequest('/outreach', { method: 'POST', body: JSON.stringify(data) }),
  updateOutreach: (id, data) => adminRequest(`/outreach/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
};
