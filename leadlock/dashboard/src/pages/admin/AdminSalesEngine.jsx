import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import { Zap, Play, Settings as SettingsIcon, BarChart3, RefreshCw, ChevronDown, ChevronUp, X, Users, Activity, Mail, Trash2, Ban, Plus, Search } from 'lucide-react';

const TRADE_TYPES = ['hvac', 'plumbing', 'roofing', 'electrical', 'solar', 'general'];
const STATUS_OPTIONS = ['cold', 'contacted', 'demo_scheduled', 'demo_completed', 'proposal_sent', 'won', 'lost'];
const JOB_STATUS_COLORS = {
  pending: '#94a3b8',
  running: '#fbbf24',
  completed: '#34d399',
  failed: '#f87171',
};
const PROSPECT_STATUS_COLORS = {
  cold: '#94a3b8',
  contacted: '#60a5fa',
  demo_scheduled: '#7c5bf0',
  demo_completed: '#a78bfa',
  proposal_sent: '#fbbf24',
  won: '#34d399',
  lost: '#f87171',
};
const HEALTH_COLORS = { healthy: '#34d399', warning: '#fbbf24', unhealthy: '#f87171', unknown: '#94a3b8' };

const inputStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
};

function MetricCard({ label, value, sub, color }) {
  return (
    <div className="glass-card p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
      <p className="text-xl font-semibold font-mono" style={{ color: color || 'var(--text-primary)' }}>{value}</p>
      {sub && <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>}
    </div>
  );
}

function StatusBadge({ status, colors }) {
  const c = colors || PROSPECT_STATUS_COLORS;
  return (
    <span className="text-[11px] font-medium px-1.5 py-0.5 rounded capitalize" style={{
      color: c[status] || '#94a3b8',
      background: `${c[status] || '#94a3b8'}15`,
    }}>{(status || '').replace('_', ' ')}</span>
  );
}

export default function AdminSalesEngine() {
  const [metrics, setMetrics] = useState(null);
  const [config, setConfig] = useState(null);
  const [scrapeJobs, setScrapeJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('metrics');
  const [showScrapeForm, setShowScrapeForm] = useState(false);
  const [scrapeForm, setScrapeForm] = useState({ city: '', state: '', trade_type: 'hvac' });
  const [scraping, setScraping] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newLocation, setNewLocation] = useState({ city: '', state: '' });

  // Prospects state
  const [prospects, setProspects] = useState([]);
  const [prospectsTotal, setProspectsTotal] = useState(0);
  const [prospectsPage, setProspectsPage] = useState(1);
  const [prospectsFilter, setProspectsFilter] = useState({ status: '', trade_type: '', search: '' });
  const [selectedProspect, setSelectedProspect] = useState(null);
  const [prospectEmails, setProspectEmails] = useState([]);

  // Worker status state
  const [workerStatus, setWorkerStatus] = useState(null);

  const fetchAll = async () => {
    try {
      const [m, c, j] = await Promise.all([
        api.getSalesMetrics(),
        api.getSalesConfig(),
        api.getScrapeJobs(),
      ]);
      setMetrics(m);
      setConfig(c);
      setScrapeJobs(j.jobs || []);
    } catch (e) {
      console.error('Failed to fetch sales engine data:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchProspects = useCallback(async () => {
    try {
      const params = { page: prospectsPage, per_page: 25 };
      if (prospectsFilter.status) params.status = prospectsFilter.status;
      if (prospectsFilter.trade_type) params.trade_type = prospectsFilter.trade_type;
      if (prospectsFilter.search) params.search = prospectsFilter.search;
      const data = await api.getProspects(params);
      setProspects(data.prospects || []);
      setProspectsTotal(data.total || 0);
    } catch (e) {
      console.error('Failed to fetch prospects:', e);
    }
  }, [prospectsPage, prospectsFilter]);

  const fetchWorkerStatus = async () => {
    try {
      const data = await api.getWorkerStatus();
      setWorkerStatus(data);
    } catch (e) {
      console.error('Failed to fetch worker status:', e);
    }
  };

  useEffect(() => { fetchAll(); }, []);
  useEffect(() => { if (activeTab === 'prospects') fetchProspects(); }, [activeTab, fetchProspects]);
  useEffect(() => { if (activeTab === 'status') fetchWorkerStatus(); }, [activeTab]);

  const handleToggle = async () => {
    try {
      await api.updateSalesConfig({ is_active: !config.is_active });
      setConfig(c => ({ ...c, is_active: !c.is_active }));
    } catch (e) {
      console.error('Failed to toggle sales engine:', e);
    }
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      await api.updateSalesConfig(config);
      await fetchAll();
    } catch (e) {
      console.error('Failed to save config:', e);
    } finally {
      setSaving(false);
    }
  };

  const handleScrape = async () => {
    if (!scrapeForm.city || !scrapeForm.state) return;
    setScraping(true);
    try {
      await api.triggerScrapeJob(scrapeForm);
      setShowScrapeForm(false);
      setScrapeForm({ city: '', state: '', trade_type: 'hvac' });
      await fetchAll();
    } catch (e) {
      console.error('Scrape failed:', e);
    } finally {
      setScraping(false);
    }
  };

  const addLocation = () => {
    if (!newLocation.city || !newLocation.state) return;
    const locations = [...(config.target_locations || []), { ...newLocation }];
    setConfig(c => ({ ...c, target_locations: locations }));
    setNewLocation({ city: '', state: '' });
  };

  const removeLocation = (idx) => {
    const locations = (config.target_locations || []).filter((_, i) => i !== idx);
    setConfig(c => ({ ...c, target_locations: locations }));
  };

  const toggleTradeType = (trade) => {
    const types = config.target_trade_types || [];
    const updated = types.includes(trade) ? types.filter(t => t !== trade) : [...types, trade];
    setConfig(c => ({ ...c, target_trade_types: updated }));
  };

  const handleSelectProspect = async (prospect) => {
    setSelectedProspect(prospect);
    try {
      const data = await api.getProspectEmails(prospect.id);
      setProspectEmails(data.emails || []);
    } catch (e) {
      console.error('Failed to fetch emails:', e);
    }
  };

  const handleDeleteProspect = async (id) => {
    try {
      await api.deleteProspect(id);
      setSelectedProspect(null);
      await fetchProspects();
    } catch (e) {
      console.error('Delete failed:', e);
    }
  };

  const handleBlacklistProspect = async (id) => {
    try {
      await api.blacklistProspect(id);
      setSelectedProspect(null);
      await fetchProspects();
    } catch (e) {
      console.error('Blacklist failed:', e);
    }
  };

  const tabs = [
    { key: 'metrics', label: 'Metrics', icon: BarChart3 },
    { key: 'prospects', label: 'Prospects', icon: Users },
    { key: 'scraping', label: 'Scrape Jobs', icon: RefreshCw },
    { key: 'status', label: 'Status', icon: Activity },
    { key: 'settings', label: 'Settings', icon: SettingsIcon },
  ];

  if (loading) {
    return <div className="h-64 rounded-card animate-pulse" style={{ background: 'var(--surface-1)' }} />;
  }

  return (
    <div className="animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Sales Engine</h1>
          <button
            onClick={handleToggle}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all"
            style={{
              background: config?.is_active ? 'rgba(52, 211, 153, 0.1)' : 'rgba(148, 163, 184, 0.1)',
              color: config?.is_active ? '#34d399' : '#94a3b8',
              border: `1px solid ${config?.is_active ? 'rgba(52, 211, 153, 0.2)' : 'rgba(148, 163, 184, 0.2)'}`,
            }}
          >
            <Zap className="w-3 h-3" />
            {config?.is_active ? 'Active' : 'Inactive'}
          </button>
        </div>
        <button
          onClick={() => { setShowScrapeForm(true); }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold text-white transition-all gradient-btn"
        >
          <Play className="w-3.5 h-3.5" />
          Run Scrape
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium rounded-md capitalize transition-all whitespace-nowrap"
            style={{
              background: activeTab === key ? 'var(--accent-muted)' : 'transparent',
              color: activeTab === key ? 'var(--accent)' : 'var(--text-tertiary)',
              border: activeTab === key ? '1px solid rgba(124, 91, 240, 0.2)' : '1px solid var(--border)',
            }}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Scrape Form Modal */}
      {showScrapeForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-xl p-6 glass-card gradient-border">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[15px] font-semibold" style={{ color: 'var(--text-primary)' }}>Run Manual Scrape</h2>
              <button onClick={() => setShowScrapeForm(false)} style={{ color: 'var(--text-tertiary)' }}><X className="w-4 h-4" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>City</label>
                <input
                  type="text" value={scrapeForm.city} onChange={e => setScrapeForm(f => ({ ...f, city: e.target.value }))}
                  className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} placeholder="Austin"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>State</label>
                <input
                  type="text" value={scrapeForm.state} onChange={e => setScrapeForm(f => ({ ...f, state: e.target.value.toUpperCase().slice(0, 2) }))}
                  className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} placeholder="TX" maxLength={2}
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Trade Type</label>
                <select value={scrapeForm.trade_type} onChange={e => setScrapeForm(f => ({ ...f, trade_type: e.target.value }))}
                  className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle}>
                  {TRADE_TYPES.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                </select>
              </div>
              <button
                onClick={handleScrape} disabled={scraping || !scrapeForm.city || !scrapeForm.state}
                className="w-full py-2.5 rounded-md text-[13px] font-medium text-white transition-all disabled:opacity-50"
                style={{ background: 'var(--accent)' }}
              >
                {scraping ? 'Scraping...' : 'Start Scrape'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Metrics Tab */}
      {activeTab === 'metrics' && metrics && (
        <div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <MetricCard label="Prospects Scraped" value={metrics.prospects?.total || 0} />
            <MetricCard label="Emails Sent" value={metrics.emails?.sent || 0} />
            <MetricCard label="Open Rate" value={`${metrics.emails?.open_rate || 0}%`} color={metrics.emails?.open_rate > 20 ? '#34d399' : '#fbbf24'} />
            <MetricCard label="Reply Rate" value={`${metrics.emails?.reply_rate || 0}%`} color={metrics.emails?.reply_rate > 5 ? '#34d399' : '#fbbf24'} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <MetricCard label="Demos Booked" value={metrics.conversions?.demos_booked || 0} color="#7c5bf0" />
            <MetricCard label="Won" value={metrics.conversions?.won || 0} color="#34d399" />
            <MetricCard label="Total Cost" value={`$${metrics.cost?.total || 0}`} />
            <MetricCard label="Bounced" value={metrics.emails?.bounced || 0} color={metrics.emails?.bounced > 0 ? '#f87171' : 'var(--text-primary)'} />
          </div>
          <div className="rounded-card p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <p className="text-[11px] font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>Pipeline Breakdown</p>
            <div className="flex flex-wrap gap-3">
              {Object.entries(metrics.prospects?.by_status || {}).map(([status, count]) => (
                <div key={status} className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: PROSPECT_STATUS_COLORS[status] || '#94a3b8' }} />
                  <span className="text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{status.replace('_', ' ')}</span>
                  <span className="text-[12px] font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Prospects Tab */}
      {activeTab === 'prospects' && (
        <div>
          {/* Filters */}
          <div className="flex gap-2 mb-4 flex-wrap">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} />
              <input
                type="text" value={prospectsFilter.search}
                onChange={e => { setProspectsFilter(f => ({ ...f, search: e.target.value })); setProspectsPage(1); }}
                className="w-full pl-8 pr-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} placeholder="Search name, company, email..."
              />
            </div>
            <select
              value={prospectsFilter.status}
              onChange={e => { setProspectsFilter(f => ({ ...f, status: e.target.value })); setProspectsPage(1); }}
              className="px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle}
            >
              <option value="">All Statuses</option>
              {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
            </select>
            <select
              value={prospectsFilter.trade_type}
              onChange={e => { setProspectsFilter(f => ({ ...f, trade_type: e.target.value })); setProspectsPage(1); }}
              className="px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle}
            >
              <option value="">All Trades</option>
              {TRADE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div className="flex gap-4">
            {/* Prospects Table */}
            <div className={`rounded-card overflow-hidden ${selectedProspect ? 'flex-1' : 'w-full'}`} style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {['Name', 'Email', 'Trade', 'Status', 'Step', 'Opened', 'Cost'].map(h => (
                        <th key={h} className="text-left px-3 py-2.5 text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {prospects.length === 0 ? (
                      <tr><td colSpan={7} className="px-4 py-12 text-center text-[13px]" style={{ color: 'var(--text-tertiary)' }}>No prospects found.</td></tr>
                    ) : prospects.map(p => (
                      <tr
                        key={p.id}
                        onClick={() => handleSelectProspect(p)}
                        className="cursor-pointer transition-colors hover:opacity-80"
                        style={{
                          borderBottom: '1px solid var(--border)',
                          background: selectedProspect?.id === p.id ? 'var(--accent-muted)' : 'transparent',
                        }}
                      >
                        <td className="px-3 py-2.5">
                          <div className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{p.prospect_name}</div>
                          {p.prospect_company && p.prospect_company !== p.prospect_name && (
                            <div className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{p.prospect_company}</div>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-[12px]" style={{ color: 'var(--text-secondary)' }}>{p.prospect_email || '—'}</td>
                        <td className="px-3 py-2.5 text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{p.prospect_trade_type}</td>
                        <td className="px-3 py-2.5"><StatusBadge status={p.status} /></td>
                        <td className="px-3 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-secondary)' }}>{p.outreach_sequence_step}/{config?.max_sequence_steps || 3}</td>
                        <td className="px-3 py-2.5 text-[12px]" style={{ color: p.last_email_opened_at ? '#34d399' : 'var(--text-tertiary)' }}>{p.last_email_opened_at ? 'Yes' : '—'}</td>
                        <td className="px-3 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-secondary)' }}>${(p.total_cost_usd || 0).toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* Pagination */}
              {prospectsTotal > 25 && (
                <div className="flex items-center justify-between px-4 py-3" style={{ borderTop: '1px solid var(--border)' }}>
                  <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{prospectsTotal} total</span>
                  <div className="flex gap-1">
                    <button disabled={prospectsPage <= 1} onClick={() => setProspectsPage(p => p - 1)}
                      className="px-2 py-1 text-[11px] rounded" style={{ ...inputStyle, opacity: prospectsPage <= 1 ? 0.4 : 1 }}>Prev</button>
                    <span className="px-2 py-1 text-[11px] font-mono" style={{ color: 'var(--text-secondary)' }}>{prospectsPage}</span>
                    <button onClick={() => setProspectsPage(p => p + 1)}
                      className="px-2 py-1 text-[11px] rounded" style={inputStyle}>Next</button>
                  </div>
                </div>
              )}
            </div>

            {/* Prospect Detail Panel */}
            {selectedProspect && (
              <div className="w-[400px] flex-shrink-0 rounded-card overflow-y-auto" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)', maxHeight: '80vh' }}>
                <div className="p-4" style={{ borderBottom: '1px solid var(--border)' }}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-[14px] font-semibold" style={{ color: 'var(--text-primary)' }}>{selectedProspect.prospect_name}</h3>
                    <button onClick={() => setSelectedProspect(null)} style={{ color: 'var(--text-tertiary)' }}><X className="w-4 h-4" /></button>
                  </div>
                  <div className="space-y-1 text-[12px]" style={{ color: 'var(--text-secondary)' }}>
                    {selectedProspect.prospect_email && <div>Email: {selectedProspect.prospect_email}</div>}
                    {selectedProspect.prospect_phone && <div>Phone: {selectedProspect.prospect_phone}</div>}
                    {selectedProspect.website && <div>Web: {selectedProspect.website}</div>}
                    {selectedProspect.city && <div>Location: {selectedProspect.city}, {selectedProspect.state_code}</div>}
                    {selectedProspect.google_rating && <div>Rating: {selectedProspect.google_rating}/5 ({selectedProspect.review_count} reviews)</div>}
                  </div>
                  <div className="flex gap-2 mt-3">
                    <button onClick={() => handleDeleteProspect(selectedProspect.id)}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded text-[11px] font-medium"
                      style={{ background: 'rgba(248, 113, 113, 0.1)', color: '#f87171', border: '1px solid rgba(248, 113, 113, 0.2)' }}>
                      <Trash2 className="w-3 h-3" /> Delete
                    </button>
                    <button onClick={() => handleBlacklistProspect(selectedProspect.id)}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded text-[11px] font-medium"
                      style={{ background: 'rgba(148, 163, 184, 0.1)', color: '#94a3b8', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
                      <Ban className="w-3 h-3" /> Blacklist
                    </button>
                  </div>
                </div>

                {/* Email Thread */}
                <div className="p-4">
                  <p className="text-[11px] font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>
                    <Mail className="w-3 h-3 inline mr-1" /> Email Thread ({prospectEmails.length})
                  </p>
                  {prospectEmails.length === 0 ? (
                    <p className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>No emails yet.</p>
                  ) : (
                    <div className="space-y-3">
                      {prospectEmails.map(email => (
                        <div key={email.id} className="rounded-lg p-3" style={{
                          background: email.direction === 'outbound' ? 'var(--surface-2)' : 'rgba(124, 91, 240, 0.05)',
                          border: `1px solid ${email.direction === 'outbound' ? 'var(--border)' : 'rgba(124, 91, 240, 0.2)'}`,
                        }}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[11px] font-medium" style={{ color: email.direction === 'outbound' ? 'var(--text-tertiary)' : '#7c5bf0' }}>
                              {email.direction === 'outbound' ? `Step ${email.sequence_step} — Sent` : 'Reply'}
                            </span>
                            <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                              {email.sent_at ? new Date(email.sent_at).toLocaleString() : ''}
                            </span>
                          </div>
                          <p className="text-[12px] font-medium mb-1" style={{ color: 'var(--text-primary)' }}>{email.subject}</p>
                          <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                            {email.body_text ? email.body_text.slice(0, 300) : ''}
                            {email.body_text && email.body_text.length > 300 ? '...' : ''}
                          </p>
                          {email.direction === 'outbound' && (
                            <div className="flex gap-2 mt-2">
                              {email.delivered_at && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(52, 211, 153, 0.1)', color: '#34d399' }}>Delivered</span>}
                              {email.opened_at && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(96, 165, 250, 0.1)', color: '#60a5fa' }}>Opened</span>}
                              {email.clicked_at && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(124, 91, 240, 0.1)', color: '#7c5bf0' }}>Clicked</span>}
                              {email.bounced_at && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(248, 113, 113, 0.1)', color: '#f87171' }}>Bounced</span>}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Scrape Jobs Tab */}
      {activeTab === 'scraping' && (
        <div className="rounded-card overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Platform', 'Trade', 'Location', 'Status', 'Found', 'New', 'Dupes', 'Cost', 'Date'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scrapeJobs.length === 0 ? (
                  <tr><td colSpan={9} className="px-4 py-12 text-center text-[13px]" style={{ color: 'var(--text-tertiary)' }}>No scrape jobs yet. Run your first scrape.</td></tr>
                ) : scrapeJobs.map(job => (
                  <tr key={job.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-4 py-2.5 text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{job.platform?.replace('_', ' ')}</td>
                    <td className="px-4 py-2.5 text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{job.trade_type}</td>
                    <td className="px-4 py-2.5 text-[12px]" style={{ color: 'var(--text-primary)' }}>{job.city}, {job.state_code}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={job.status} colors={JOB_STATUS_COLORS} /></td>
                    <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-secondary)' }}>{job.results_found}</td>
                    <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: '#34d399' }}>{job.new_prospects_created}</td>
                    <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{job.duplicates_skipped}</td>
                    <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: 'var(--text-secondary)' }}>${job.api_cost_usd?.toFixed(3)}</td>
                    <td className="px-4 py-2.5 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{job.created_at ? new Date(job.created_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Status Tab */}
      {activeTab === 'status' && (
        <div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            {workerStatus?.workers && Object.entries(workerStatus.workers).map(([name, info]) => (
              <div key={name} className="rounded-lg p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: HEALTH_COLORS[info.health] || '#94a3b8' }} />
                  <span className="text-[12px] font-medium capitalize" style={{ color: 'var(--text-primary)' }}>{name.replace('_', ' ')}</span>
                </div>
                <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                  {info.health === 'unknown' ? 'No heartbeat' :
                    info.last_heartbeat ? `Last: ${new Date(info.last_heartbeat).toLocaleTimeString()}` : 'N/A'}
                </p>
                <p className="text-[11px] capitalize font-medium mt-1" style={{ color: HEALTH_COLORS[info.health] }}>
                  {info.health}
                </p>
              </div>
            ))}
          </div>
          {workerStatus?.alerts && (
            <div className="rounded-card p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <p className="text-[11px] font-medium uppercase tracking-wider mb-2" style={{ color: 'var(--text-tertiary)' }}>Alerts</p>
              <div className="flex items-center gap-2">
                <span className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>Bounce Rate:</span>
                <span className="text-[12px] font-mono font-medium" style={{ color: workerStatus.alerts.bounce_rate_alert ? '#f87171' : '#34d399' }}>
                  {workerStatus.alerts.bounce_rate || 0}%
                </span>
                {workerStatus.alerts.bounce_rate_alert && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(248, 113, 113, 0.1)', color: '#f87171' }}>HIGH</span>
                )}
              </div>
            </div>
          )}
          {!workerStatus && (
            <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>Loading worker status...</p>
          )}
        </div>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && config && (
        <div className="space-y-5">
          {/* Target Locations */}
          <div className="rounded-card p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <p className="text-[13px] font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>Target Locations</p>
            <div className="flex flex-wrap gap-2 mb-3">
              {(config.target_locations || []).map((loc, i) => (
                <span key={i} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[12px]" style={{ background: 'var(--surface-3)', color: 'var(--text-secondary)' }}>
                  {loc.city}, {loc.state}
                  <button onClick={() => removeLocation(i)} className="ml-0.5" style={{ color: 'var(--text-tertiary)' }}><X className="w-3 h-3" /></button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input type="text" value={newLocation.city} onChange={e => setNewLocation(l => ({ ...l, city: e.target.value }))}
                className="flex-1 px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} placeholder="City" />
              <input type="text" value={newLocation.state} onChange={e => setNewLocation(l => ({ ...l, state: e.target.value.toUpperCase().slice(0, 2) }))}
                className="w-16 px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} placeholder="ST" maxLength={2} />
              <button onClick={addLocation} className="px-3 py-2 rounded-md text-[12px] font-medium text-white" style={{ background: 'var(--accent)' }}>Add</button>
            </div>
          </div>

          {/* Target Trade Types */}
          <div className="rounded-card p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <p className="text-[13px] font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>Target Trade Types</p>
            <div className="flex flex-wrap gap-2">
              {TRADE_TYPES.map(trade => {
                const active = (config.target_trade_types || []).includes(trade);
                return (
                  <button key={trade} onClick={() => toggleTradeType(trade)}
                    className="px-3 py-1.5 rounded-md text-[12px] font-medium capitalize transition-all"
                    style={{
                      background: active ? 'var(--accent-muted)' : 'var(--surface-2)',
                      color: active ? 'var(--accent)' : 'var(--text-tertiary)',
                      border: `1px solid ${active ? 'rgba(124, 91, 240, 0.3)' : 'var(--border)'}`,
                    }}
                  >
                    {trade}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Limits */}
          <div className="rounded-card p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <p className="text-[13px] font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>Limits</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Daily Emails', key: 'daily_email_limit' },
                { label: 'Daily Scrapes', key: 'daily_scrape_limit' },
                { label: 'Delay (hours)', key: 'sequence_delay_hours' },
                { label: 'Max Steps', key: 'max_sequence_steps' },
              ].map(({ label, key }) => (
                <div key={key}>
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>{label}</label>
                  <input type="number" value={config[key] || ''} onChange={e => setConfig(c => ({ ...c, [key]: parseInt(e.target.value) || 0 }))}
                    className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} />
                </div>
              ))}
            </div>
          </div>

          {/* Email Sender */}
          <div className="rounded-card p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <p className="text-[13px] font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>Email Sender</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                { label: 'From Email', key: 'from_email', placeholder: 'outreach@leadlock.io' },
                { label: 'From Name', key: 'from_name', placeholder: 'LeadLock' },
                { label: 'Reply-To Email', key: 'reply_to_email', placeholder: 'alex@leadlock.io' },
                { label: 'Company Address', key: 'company_address', placeholder: '123 Main St, Austin, TX 78701' },
              ].map(({ label, key, placeholder }) => (
                <div key={key}>
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>{label}</label>
                  <input type="text" value={config[key] || ''} onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} placeholder={placeholder} />
                </div>
              ))}
            </div>
          </div>

          <button onClick={handleSaveConfig} disabled={saving}
            className="px-5 py-2.5 rounded-md text-[13px] font-medium text-white transition-all disabled:opacity-50"
            style={{ background: 'var(--accent)' }}>
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      )}
    </div>
  );
}
