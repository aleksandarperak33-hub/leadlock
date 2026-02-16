import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import { Zap, Play, Settings as SettingsIcon, BarChart3, RefreshCw, ChevronDown, ChevronUp, X, Users, Activity, Mail, Trash2, Ban, Plus, Search } from 'lucide-react';

const TRADE_TYPES = ['hvac', 'plumbing', 'roofing', 'electrical', 'solar', 'general'];
const STATUS_OPTIONS = ['cold', 'contacted', 'demo_scheduled', 'demo_completed', 'proposal_sent', 'won', 'lost'];

const JOB_STATUS_BADGE = {
  pending: 'bg-gray-50 text-gray-600 border border-gray-100',
  running: 'bg-amber-50 text-amber-700 border border-amber-100',
  completed: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  failed: 'bg-red-50 text-red-700 border border-red-100',
};

const PROSPECT_STATUS_BADGE = {
  cold: 'bg-gray-50 text-gray-600 border border-gray-100',
  contacted: 'bg-blue-50 text-blue-700 border border-blue-100',
  demo_scheduled: 'bg-violet-50 text-violet-700 border border-violet-100',
  demo_completed: 'bg-purple-50 text-purple-700 border border-purple-100',
  proposal_sent: 'bg-amber-50 text-amber-700 border border-amber-100',
  won: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  lost: 'bg-red-50 text-red-700 border border-red-100',
};

const PROSPECT_STATUS_DOT = {
  cold: 'bg-gray-400',
  contacted: 'bg-blue-500',
  demo_scheduled: 'bg-violet-500',
  demo_completed: 'bg-purple-500',
  proposal_sent: 'bg-amber-500',
  won: 'bg-emerald-500',
  lost: 'bg-red-500',
};

const HEALTH_COLORS = {
  healthy: 'bg-emerald-500',
  warning: 'bg-amber-500',
  unhealthy: 'bg-red-500',
  unknown: 'bg-gray-400',
};

const HEALTH_TEXT = {
  healthy: 'text-emerald-700',
  warning: 'text-amber-700',
  unhealthy: 'text-red-700',
  unknown: 'text-gray-500',
};

function MetricCard({ label, value, sub, variant }) {
  const textColor = variant === 'success' ? 'text-emerald-600'
    : variant === 'warning' ? 'text-amber-600'
    : variant === 'danger' ? 'text-red-600'
    : variant === 'accent' ? 'text-violet-600'
    : 'text-gray-900';

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">{label}</p>
      <p className={`text-xl font-semibold font-mono ${textColor}`}>{value}</p>
      {sub && <p className="text-xs mt-0.5 text-gray-400">{sub}</p>}
    </div>
  );
}

function StatusBadge({ status, type }) {
  const styles = type === 'job' ? JOB_STATUS_BADGE : PROSPECT_STATUS_BADGE;
  const cls = styles[status] || 'bg-gray-50 text-gray-600 border border-gray-100';
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-md capitalize ${cls}`}>
      {(status || '').replace('_', ' ')}
    </span>
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
    return <div className="h-64 bg-gray-100 rounded-xl animate-pulse" />;
  }

  return (
    <div style={{ backgroundColor: '#f8f9fb' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight text-gray-900">Sales Engine</h1>
          <button
            onClick={handleToggle}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all cursor-pointer ${
              config?.is_active
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'bg-gray-50 text-gray-500 border border-gray-200'
            }`}
          >
            <Zap className="w-3 h-3" />
            {config?.is_active ? 'Active' : 'Inactive'}
          </button>
        </div>
        <button
          onClick={() => { setShowScrapeForm(true); }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-violet-600 hover:bg-violet-700 transition-colors cursor-pointer"
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
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg capitalize transition-all whitespace-nowrap cursor-pointer ${
              activeTab === key
                ? 'bg-violet-50 text-violet-700 border border-violet-200'
                : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300 hover:text-gray-700'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Scrape Form Modal */}
      {showScrapeForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm bg-white border border-gray-200 rounded-xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-gray-900">Run Manual Scrape</h2>
              <button onClick={() => setShowScrapeForm(false)} className="text-gray-400 hover:text-gray-600 cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">City</label>
                <input
                  type="text" value={scrapeForm.city} onChange={e => setScrapeForm(f => ({ ...f, city: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all"
                  placeholder="Austin"
                />
              </div>
              <div>
                <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">State</label>
                <input
                  type="text" value={scrapeForm.state} onChange={e => setScrapeForm(f => ({ ...f, state: e.target.value.toUpperCase().slice(0, 2) }))}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all"
                  placeholder="TX" maxLength={2}
                />
              </div>
              <div>
                <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">Trade Type</label>
                <select value={scrapeForm.trade_type} onChange={e => setScrapeForm(f => ({ ...f, trade_type: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all cursor-pointer">
                  {TRADE_TYPES.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                </select>
              </div>
              <button
                onClick={handleScrape} disabled={scraping || !scrapeForm.city || !scrapeForm.state}
                className="w-full py-2.5 rounded-lg text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 transition-colors disabled:opacity-50 cursor-pointer"
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
            <MetricCard label="Open Rate" value={`${metrics.emails?.open_rate || 0}%`} variant={metrics.emails?.open_rate > 20 ? 'success' : 'warning'} />
            <MetricCard label="Reply Rate" value={`${metrics.emails?.reply_rate || 0}%`} variant={metrics.emails?.reply_rate > 5 ? 'success' : 'warning'} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <MetricCard label="Demos Booked" value={metrics.conversions?.demos_booked || 0} variant="accent" />
            <MetricCard label="Won" value={metrics.conversions?.won || 0} variant="success" />
            <MetricCard label="Total Cost" value={`$${metrics.cost?.total || 0}`} />
            <MetricCard label="Bounced" value={metrics.emails?.bounced || 0} variant={metrics.emails?.bounced > 0 ? 'danger' : undefined} />
          </div>
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">Pipeline Breakdown</p>
            <div className="flex flex-wrap gap-3">
              {Object.entries(metrics.prospects?.by_status || {}).map(([status, count]) => (
                <div key={status} className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${PROSPECT_STATUS_DOT[status] || 'bg-gray-400'}`} />
                  <span className="text-xs capitalize text-gray-500">{status.replace('_', ' ')}</span>
                  <span className="text-xs font-mono font-medium text-gray-900">{count}</span>
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
              <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text" value={prospectsFilter.search}
                onChange={e => { setProspectsFilter(f => ({ ...f, search: e.target.value })); setProspectsPage(1); }}
                className="w-full pl-8 pr-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all"
                placeholder="Search name, company, email..."
              />
            </div>
            <select
              value={prospectsFilter.status}
              onChange={e => { setProspectsFilter(f => ({ ...f, status: e.target.value })); setProspectsPage(1); }}
              className="px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all cursor-pointer"
            >
              <option value="">All Statuses</option>
              {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
            </select>
            <select
              value={prospectsFilter.trade_type}
              onChange={e => { setProspectsFilter(f => ({ ...f, trade_type: e.target.value })); setProspectsPage(1); }}
              className="px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all cursor-pointer"
            >
              <option value="">All Trades</option>
              {TRADE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div className="flex gap-4">
            {/* Prospects Table */}
            <div className={`bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden ${selectedProspect ? 'flex-1' : 'w-full'}`}>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      {['Name', 'Email', 'Trade', 'Status', 'Step', 'Opened', 'Cost'].map(h => (
                        <th key={h} className="text-left px-3 py-2.5 text-xs font-medium uppercase tracking-wider text-gray-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {prospects.length === 0 ? (
                      <tr><td colSpan={7} className="px-4 py-12 text-center text-sm text-gray-400">No prospects found.</td></tr>
                    ) : prospects.map(p => (
                      <tr
                        key={p.id}
                        onClick={() => handleSelectProspect(p)}
                        className={`cursor-pointer transition-colors border-b border-gray-100 ${
                          selectedProspect?.id === p.id ? 'bg-violet-50' : 'hover:bg-gray-50'
                        }`}
                      >
                        <td className="px-3 py-2.5">
                          <div className="text-xs font-medium text-gray-900">{p.prospect_name}</div>
                          {p.prospect_company && p.prospect_company !== p.prospect_name && (
                            <div className="text-xs text-gray-400">{p.prospect_company}</div>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-gray-500">{p.prospect_email || '\u2014'}</td>
                        <td className="px-3 py-2.5 text-xs capitalize text-gray-500">{p.prospect_trade_type}</td>
                        <td className="px-3 py-2.5"><StatusBadge status={p.status} /></td>
                        <td className="px-3 py-2.5 text-xs font-mono text-gray-500">{p.outreach_sequence_step}/{config?.max_sequence_steps || 3}</td>
                        <td className="px-3 py-2.5 text-xs">
                          {p.last_email_opened_at
                            ? <span className="text-emerald-600 font-medium">Yes</span>
                            : <span className="text-gray-400">\u2014</span>
                          }
                        </td>
                        <td className="px-3 py-2.5 text-xs font-mono text-gray-500">${(p.total_cost_usd || 0).toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* Pagination */}
              {prospectsTotal > 25 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
                  <span className="text-xs text-gray-400">{prospectsTotal} total</span>
                  <div className="flex gap-1">
                    <button disabled={prospectsPage <= 1} onClick={() => setProspectsPage(p => p - 1)}
                      className="px-2.5 py-1 text-xs rounded-lg bg-white border border-gray-200 text-gray-600 hover:border-gray-300 disabled:opacity-40 cursor-pointer transition-colors">
                      Prev
                    </button>
                    <span className="px-2 py-1 text-xs font-mono text-gray-500">{prospectsPage}</span>
                    <button onClick={() => setProspectsPage(p => p + 1)}
                      className="px-2.5 py-1 text-xs rounded-lg bg-white border border-gray-200 text-gray-600 hover:border-gray-300 cursor-pointer transition-colors">
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Prospect Detail Panel */}
            {selectedProspect && (
              <div className="w-[400px] flex-shrink-0 bg-white border border-gray-200 rounded-xl shadow-sm overflow-y-auto" style={{ maxHeight: '80vh' }}>
                <div className="p-4 border-b border-gray-100">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-gray-900">{selectedProspect.prospect_name}</h3>
                    <button onClick={() => setSelectedProspect(null)} className="text-gray-400 hover:text-gray-600 cursor-pointer">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="space-y-1 text-xs text-gray-500">
                    {selectedProspect.prospect_email && <div>Email: {selectedProspect.prospect_email}</div>}
                    {selectedProspect.prospect_phone && <div>Phone: {selectedProspect.prospect_phone}</div>}
                    {selectedProspect.website && <div>Web: {selectedProspect.website}</div>}
                    {selectedProspect.city && <div>Location: {selectedProspect.city}, {selectedProspect.state_code}</div>}
                    {selectedProspect.google_rating && <div>Rating: {selectedProspect.google_rating}/5 ({selectedProspect.review_count} reviews)</div>}
                  </div>
                  <div className="flex gap-2 mt-3">
                    <button onClick={() => handleDeleteProspect(selectedProspect.id)}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-red-50 text-red-700 border border-red-100 hover:bg-red-100 cursor-pointer transition-colors">
                      <Trash2 className="w-3 h-3" /> Delete
                    </button>
                    <button onClick={() => handleBlacklistProspect(selectedProspect.id)}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-gray-50 text-gray-600 border border-gray-200 hover:bg-gray-100 cursor-pointer transition-colors">
                      <Ban className="w-3 h-3" /> Blacklist
                    </button>
                  </div>
                </div>

                {/* Email Thread */}
                <div className="p-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">
                    <Mail className="w-3 h-3 inline mr-1" /> Email Thread ({prospectEmails.length})
                  </p>
                  {prospectEmails.length === 0 ? (
                    <p className="text-xs text-gray-400">No emails yet.</p>
                  ) : (
                    <div className="space-y-3">
                      {prospectEmails.map(email => (
                        <div key={email.id} className={`rounded-lg p-3 border ${
                          email.direction === 'outbound'
                            ? 'bg-gray-50 border-gray-100'
                            : 'bg-violet-50 border-violet-100'
                        }`}>
                          <div className="flex items-center justify-between mb-1">
                            <span className={`text-xs font-medium ${
                              email.direction === 'outbound' ? 'text-gray-500' : 'text-violet-600'
                            }`}>
                              {email.direction === 'outbound' ? `Step ${email.sequence_step} \u2014 Sent` : 'Reply'}
                            </span>
                            <span className="text-[10px] text-gray-400">
                              {email.sent_at ? new Date(email.sent_at).toLocaleString() : ''}
                            </span>
                          </div>
                          <p className="text-xs font-medium mb-1 text-gray-900">{email.subject}</p>
                          <p className="text-xs leading-relaxed text-gray-500">
                            {email.body_text ? email.body_text.slice(0, 300) : ''}
                            {email.body_text && email.body_text.length > 300 ? '...' : ''}
                          </p>
                          {email.direction === 'outbound' && (
                            <div className="flex gap-2 mt-2">
                              {email.delivered_at && <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-100">Delivered</span>}
                              {email.opened_at && <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-100">Opened</span>}
                              {email.clicked_at && <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-violet-50 text-violet-700 border border-violet-100">Clicked</span>}
                              {email.bounced_at && <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-red-50 text-red-700 border border-red-100">Bounced</span>}
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
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  {['Platform', 'Trade', 'Location', 'Status', 'Found', 'New', 'Dupes', 'Cost', 'Date'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scrapeJobs.length === 0 ? (
                  <tr><td colSpan={9} className="px-4 py-12 text-center text-sm text-gray-400">No scrape jobs yet. Run your first scrape.</td></tr>
                ) : scrapeJobs.map(job => (
                  <tr key={job.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-2.5 text-xs capitalize text-gray-500">{job.platform?.replace('_', ' ')}</td>
                    <td className="px-4 py-2.5 text-xs capitalize text-gray-500">{job.trade_type}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-900">{job.city}, {job.state_code}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={job.status} type="job" /></td>
                    <td className="px-4 py-2.5 text-xs font-mono text-gray-500">{job.results_found}</td>
                    <td className="px-4 py-2.5 text-xs font-mono text-emerald-600">{job.new_prospects_created}</td>
                    <td className="px-4 py-2.5 text-xs font-mono text-gray-400">{job.duplicates_skipped}</td>
                    <td className="px-4 py-2.5 text-xs font-mono text-gray-500">${job.api_cost_usd?.toFixed(3)}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-400">{job.created_at ? new Date(job.created_at).toLocaleDateString() : '\u2014'}</td>
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
              <div key={name} className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`w-2.5 h-2.5 rounded-full ${HEALTH_COLORS[info.health] || 'bg-gray-400'}`} />
                  <span className="text-xs font-medium capitalize text-gray-900">{name.replace('_', ' ')}</span>
                </div>
                <p className="text-xs text-gray-400">
                  {info.health === 'unknown' ? 'No heartbeat' :
                    info.last_heartbeat ? `Last: ${new Date(info.last_heartbeat).toLocaleTimeString()}` : 'N/A'}
                </p>
                <p className={`text-xs capitalize font-medium mt-1 ${HEALTH_TEXT[info.health] || 'text-gray-500'}`}>
                  {info.health}
                </p>
              </div>
            ))}
          </div>
          {workerStatus?.alerts && (
            <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
              <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-2">Alerts</p>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Bounce Rate:</span>
                <span className={`text-xs font-mono font-medium ${workerStatus.alerts.bounce_rate_alert ? 'text-red-600' : 'text-emerald-600'}`}>
                  {workerStatus.alerts.bounce_rate || 0}%
                </span>
                {workerStatus.alerts.bounce_rate_alert && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-red-50 text-red-700 border border-red-100">HIGH</span>
                )}
              </div>
            </div>
          )}
          {!workerStatus && (
            <p className="text-sm text-gray-400">Loading worker status...</p>
          )}
        </div>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && config && (
        <div className="space-y-5">
          {/* Target Locations */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
            <p className="text-sm font-semibold text-gray-900 mb-3">Target Locations</p>
            <div className="flex flex-wrap gap-2 mb-3">
              {(config.target_locations || []).map((loc, i) => (
                <span key={i} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs bg-gray-100 text-gray-600 border border-gray-200">
                  {loc.city}, {loc.state}
                  <button onClick={() => removeLocation(i)} className="ml-0.5 text-gray-400 hover:text-gray-600 cursor-pointer">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input type="text" value={newLocation.city} onChange={e => setNewLocation(l => ({ ...l, city: e.target.value }))}
                className="flex-1 px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all"
                placeholder="City" />
              <input type="text" value={newLocation.state} onChange={e => setNewLocation(l => ({ ...l, state: e.target.value.toUpperCase().slice(0, 2) }))}
                className="w-16 px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all"
                placeholder="ST" maxLength={2} />
              <button onClick={addLocation}
                className="px-3 py-2 rounded-lg text-xs font-medium text-white bg-violet-600 hover:bg-violet-700 cursor-pointer transition-colors">
                Add
              </button>
            </div>
          </div>

          {/* Target Trade Types */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
            <p className="text-sm font-semibold text-gray-900 mb-3">Target Trade Types</p>
            <div className="flex flex-wrap gap-2">
              {TRADE_TYPES.map(trade => {
                const active = (config.target_trade_types || []).includes(trade);
                return (
                  <button key={trade} onClick={() => toggleTradeType(trade)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all cursor-pointer ${
                      active
                        ? 'bg-violet-50 text-violet-700 border border-violet-200'
                        : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    {trade}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Limits */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
            <p className="text-sm font-semibold text-gray-900 mb-3">Limits</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Daily Emails', key: 'daily_email_limit' },
                { label: 'Daily Scrapes', key: 'daily_scrape_limit' },
                { label: 'Delay (hours)', key: 'sequence_delay_hours' },
                { label: 'Max Steps', key: 'max_sequence_steps' },
              ].map(({ label, key }) => (
                <div key={key}>
                  <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">{label}</label>
                  <input type="number" value={config[key] || ''} onChange={e => setConfig(c => ({ ...c, [key]: parseInt(e.target.value) || 0 }))}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all" />
                </div>
              ))}
            </div>
          </div>

          {/* Email Sender */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
            <p className="text-sm font-semibold text-gray-900 mb-3">Email Sender</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                { label: 'From Email', key: 'from_email', placeholder: 'outreach@leadlock.io' },
                { label: 'From Name', key: 'from_name', placeholder: 'LeadLock' },
                { label: 'Reply-To Email', key: 'reply_to_email', placeholder: 'alex@leadlock.io' },
                { label: 'Company Address', key: 'company_address', placeholder: '123 Main St, Austin, TX 78701' },
              ].map(({ label, key, placeholder }) => (
                <div key={key}>
                  <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">{label}</label>
                  <input type="text" value={config[key] || ''} onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-all"
                    placeholder={placeholder} />
                </div>
              ))}
            </div>
          </div>

          <button onClick={handleSaveConfig} disabled={saving}
            className="px-5 py-2.5 rounded-lg text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 transition-colors disabled:opacity-50 cursor-pointer">
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      )}
    </div>
  );
}
