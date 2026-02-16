import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { Zap, Play, Settings as SettingsIcon, BarChart3, RefreshCw, ChevronDown, ChevronUp, X } from 'lucide-react';

const TRADE_TYPES = ['hvac', 'plumbing', 'roofing', 'electrical', 'solar', 'general'];
const JOB_STATUS_COLORS = {
  pending: '#94a3b8',
  running: '#fbbf24',
  completed: '#34d399',
  failed: '#f87171',
};

const inputStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
};

function MetricCard({ label, value, sub, color }) {
  return (
    <div className="rounded-lg p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      <p className="text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
      <p className="text-xl font-semibold font-mono" style={{ color: color || 'var(--text-primary)' }}>{value}</p>
      {sub && <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>}
    </div>
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

  useEffect(() => { fetchAll(); }, []);

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

  const tabs = [
    { key: 'metrics', label: 'Metrics', icon: BarChart3 },
    { key: 'scraping', label: 'Scrape Jobs', icon: RefreshCw },
    { key: 'settings', label: 'Settings', icon: SettingsIcon },
  ];

  if (loading) {
    return <div className="h-64 rounded-card animate-pulse" style={{ background: 'var(--surface-1)' }} />;
  }

  return (
    <div>
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
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium text-white transition-all"
          style={{ background: 'var(--accent)' }}
        >
          <Play className="w-3.5 h-3.5" />
          Run Scrape
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium rounded-md capitalize transition-all"
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
          <div className="w-full max-w-sm rounded-xl p-6" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
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
          {/* Status breakdown */}
          <div className="rounded-card p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <p className="text-[11px] font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>Pipeline Breakdown</p>
            <div className="flex flex-wrap gap-3">
              {Object.entries(metrics.prospects?.by_status || {}).map(([status, count]) => (
                <div key={status} className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: JOB_STATUS_COLORS[status] || '#94a3b8' }} />
                  <span className="text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{status.replace('_', ' ')}</span>
                  <span className="text-[12px] font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{count}</span>
                </div>
              ))}
            </div>
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
                    <td className="px-4 py-2.5">
                      <span className="text-[11px] font-medium px-1.5 py-0.5 rounded capitalize" style={{
                        color: JOB_STATUS_COLORS[job.status],
                        background: `${JOB_STATUS_COLORS[job.status]}15`,
                      }}>{job.status}</span>
                    </td>
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

          {/* Save button */}
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
