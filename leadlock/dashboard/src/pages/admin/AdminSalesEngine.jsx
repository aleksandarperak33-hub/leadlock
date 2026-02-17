import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import {
  Zap, Play, X, Users, Mail, Trash2, Ban, Plus,
} from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import StatCard from '../../components/ui/StatCard';
import Badge from '../../components/ui/Badge';
import DataTable from '../../components/ui/DataTable';
import Tabs from '../../components/ui/Tabs';
import SearchInput from '../../components/ui/SearchInput';
import StatusDot from '../../components/ui/StatusDot';
import EmptyState from '../../components/ui/EmptyState';
import SalesEngineSettings from './SalesEngineSettings';

const TRADE_TYPES = ['hvac', 'plumbing', 'roofing', 'electrical', 'solar', 'general'];
const STATUS_OPTIONS = ['cold', 'contacted', 'demo_scheduled', 'demo_completed', 'proposal_sent', 'won', 'lost'];

const INPUT_CLASSES = 'bg-white border border-gray-200 text-gray-900 outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-100 transition-all';

const JOB_STATUS_VARIANT = {
  pending: 'neutral',
  running: 'warning',
  completed: 'success',
  failed: 'danger',
};

const PROSPECT_STATUS_VARIANT = {
  cold: 'neutral',
  contacted: 'info',
  demo_scheduled: 'warning',
  demo_completed: 'warning',
  proposal_sent: 'warning',
  won: 'success',
  lost: 'danger',
};

const PROSPECT_DOT_COLOR = {
  cold: 'gray',
  contacted: 'yellow',
  demo_scheduled: 'yellow',
  demo_completed: 'yellow',
  proposal_sent: 'yellow',
  won: 'green',
  lost: 'red',
};

const HEALTH_DOT_MAP = {
  healthy: 'green',
  warning: 'yellow',
  unhealthy: 'red',
  unknown: 'gray',
};

function formatStatus(status) {
  return (status || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ---------- Scrape Form Modal ---------- */

function ScrapeFormModal({ show, form, onChange, onSubmit, onClose, scraping }) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm bg-white border border-gray-200/60 rounded-2xl shadow-lg p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-900">Run Manual Scrape</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">City</label>
            <input
              type="text"
              value={form.city}
              onChange={(e) => onChange({ ...form, city: e.target.value })}
              className={`w-full px-3 py-2.5 rounded-xl text-sm ${INPUT_CLASSES}`}
              placeholder="Austin"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">State</label>
            <input
              type="text"
              value={form.state}
              onChange={(e) => onChange({ ...form, state: e.target.value.toUpperCase().slice(0, 2) })}
              className={`w-full px-3 py-2.5 rounded-xl text-sm ${INPUT_CLASSES}`}
              placeholder="TX"
              maxLength={2}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Trade Type</label>
            <select
              value={form.trade_type}
              onChange={(e) => onChange({ ...form, trade_type: e.target.value })}
              className={`w-full px-3 py-2.5 rounded-xl text-sm cursor-pointer ${INPUT_CLASSES}`}
            >
              {TRADE_TYPES.map((t) => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>
          </div>
          <button
            onClick={onSubmit}
            disabled={scraping || !form.city || !form.state}
            className="w-full py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors disabled:opacity-50 cursor-pointer"
          >
            {scraping ? 'Scraping...' : 'Start Scrape'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Metrics Tab ---------- */

function MetricsTab({ metrics }) {
  if (!metrics) return null;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Prospects Scraped" value={metrics.prospects?.total || 0} />
        <StatCard label="Emails Sent" value={metrics.emails?.sent || 0} />
        <StatCard
          label="Open Rate"
          value={`${metrics.emails?.open_rate || 0}%`}
          color={metrics.emails?.open_rate > 20 ? 'green' : 'yellow'}
        />
        <StatCard
          label="Reply Rate"
          value={`${metrics.emails?.reply_rate || 0}%`}
          color={metrics.emails?.reply_rate > 5 ? 'green' : 'yellow'}
        />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Demos Booked" value={metrics.conversions?.demos_booked || 0} color="brand" />
        <StatCard label="Won" value={metrics.conversions?.won || 0} color="green" />
        <StatCard label="Total Cost" value={`$${metrics.cost?.total || 0}`} />
        <StatCard
          label="Bounced"
          value={metrics.emails?.bounced || 0}
          color={metrics.emails?.bounced > 0 ? 'red' : 'brand'}
        />
      </div>
      <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">Pipeline Breakdown</p>
        <div className="flex flex-wrap gap-4">
          {Object.entries(metrics.prospects?.by_status || {}).map(([status, count]) => (
            <div key={status} className="flex items-center gap-2">
              <StatusDot color={PROSPECT_DOT_COLOR[status] || 'gray'} />
              <span className="text-sm capitalize text-gray-600">{formatStatus(status)}</span>
              <span className="text-sm font-mono font-medium text-gray-900">{count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---------- Prospects Tab ---------- */

function ProspectsTab({
  prospects, prospectsTotal, prospectsPage, prospectsFilter,
  onFilterChange, onPageChange, selectedProspect, prospectEmails,
  onSelectProspect, onCloseDetail, onDeleteProspect, onBlacklistProspect,
  maxSequenceSteps,
}) {
  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="flex-1 min-w-[220px]">
          <SearchInput
            value={prospectsFilter.search}
            onChange={(val) => { onFilterChange({ ...prospectsFilter, search: val }); onPageChange(1); }}
            placeholder="Search name, company, email..."
          />
        </div>
        <select
          value={prospectsFilter.status}
          onChange={(e) => { onFilterChange({ ...prospectsFilter, status: e.target.value }); onPageChange(1); }}
          className={`px-3 py-2.5 rounded-xl text-sm cursor-pointer ${INPUT_CLASSES}`}
        >
          <option value="">All Statuses</option>
          {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{formatStatus(s)}</option>)}
        </select>
        <select
          value={prospectsFilter.trade_type}
          onChange={(e) => { onFilterChange({ ...prospectsFilter, trade_type: e.target.value }); onPageChange(1); }}
          className={`px-3 py-2.5 rounded-xl text-sm cursor-pointer ${INPUT_CLASSES}`}
        >
          <option value="">All Trades</option>
          {TRADE_TYPES.map((t) => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
        </select>
      </div>

      <div className="flex gap-4">
        {/* Table */}
        <div className={`${selectedProspect ? 'flex-1' : 'w-full'}`}>
          <ProspectsTable
            prospects={prospects}
            selectedId={selectedProspect?.id}
            onSelect={onSelectProspect}
            maxSteps={maxSequenceSteps}
          />
          {prospectsTotal > 25 && (
            <div className="flex items-center justify-between px-4 py-3 mt-2">
              <span className="text-xs text-gray-400 font-mono">{prospectsTotal} total</span>
              <div className="flex gap-1">
                <button
                  disabled={prospectsPage <= 1}
                  onClick={() => onPageChange(prospectsPage - 1)}
                  className="px-3 py-1.5 text-xs font-medium rounded-xl bg-white border border-gray-200 text-gray-600 hover:border-gray-300 disabled:opacity-40 cursor-pointer transition-colors"
                >
                  Prev
                </button>
                <span className="px-2.5 py-1.5 text-xs font-mono text-gray-500">{prospectsPage}</span>
                <button
                  onClick={() => onPageChange(prospectsPage + 1)}
                  className="px-3 py-1.5 text-xs font-medium rounded-xl bg-white border border-gray-200 text-gray-600 hover:border-gray-300 cursor-pointer transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Detail Panel */}
        {selectedProspect && (
          <ProspectDetailPanel
            prospect={selectedProspect}
            emails={prospectEmails}
            onClose={onCloseDetail}
            onDelete={onDeleteProspect}
            onBlacklist={onBlacklistProspect}
          />
        )}
      </div>
    </div>
  );
}

function ProspectsTable({ prospects, selectedId, onSelect, maxSteps }) {
  const columns = [
    {
      key: 'prospect_name',
      label: 'Name',
      render: (val, row) => (
        <div>
          <div className="text-sm font-medium text-gray-900">{val}</div>
          {row.prospect_company && row.prospect_company !== val && (
            <div className="text-xs text-gray-400">{row.prospect_company}</div>
          )}
        </div>
      ),
    },
    { key: 'prospect_email', label: 'Email', render: (val) => <span className="text-gray-500">{val || '\u2014'}</span> },
    { key: 'prospect_trade_type', label: 'Trade', render: (val) => <span className="text-gray-500 capitalize">{val}</span> },
    {
      key: 'status',
      label: 'Status',
      render: (val) => <Badge variant={PROSPECT_STATUS_VARIANT[val] || 'neutral'} size="sm">{formatStatus(val)}</Badge>,
    },
    {
      key: 'outreach_sequence_step',
      label: 'Step',
      render: (val) => <span className="font-mono text-gray-500">{val}/{maxSteps || 3}</span>,
    },
    {
      key: 'last_email_opened_at',
      label: 'Opened',
      render: (val) => val
        ? <span className="text-emerald-600 font-medium">Yes</span>
        : <span className="text-gray-400">{'\u2014'}</span>,
    },
    {
      key: 'total_cost_usd',
      label: 'Cost',
      align: 'right',
      render: (val) => <span className="font-mono text-gray-500">${(val || 0).toFixed(3)}</span>,
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={prospects}
      emptyMessage="No prospects found."
      onRowClick={onSelect}
    />
  );
}

function ProspectDetailPanel({ prospect, emails, onClose, onDelete, onBlacklist }) {
  return (
    <div className="w-[400px] flex-shrink-0 bg-white border border-gray-200/60 rounded-2xl shadow-sm overflow-y-auto" style={{ maxHeight: '80vh' }}>
      <div className="p-5 border-b border-gray-100">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-900">{prospect.prospect_name}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="space-y-1 text-sm text-gray-500">
          {prospect.prospect_email && <div>Email: {prospect.prospect_email}</div>}
          {prospect.prospect_phone && <div>Phone: <span className="font-mono">{prospect.prospect_phone}</span></div>}
          {prospect.website && <div>Web: {prospect.website}</div>}
          {prospect.city && <div>Location: {prospect.city}, {prospect.state_code}</div>}
          {prospect.google_rating && <div>Rating: <span className="font-mono">{prospect.google_rating}/5</span> ({prospect.review_count} reviews)</div>}
        </div>
        <div className="flex gap-2 mt-4">
          <button
            onClick={() => onDelete(prospect.id)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium bg-red-50 text-red-700 border border-red-200/60 hover:bg-red-100 cursor-pointer transition-colors"
          >
            <Trash2 className="w-3 h-3" /> Delete
          </button>
          <button
            onClick={() => onBlacklist(prospect.id)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium bg-gray-50 text-gray-600 border border-gray-200/60 hover:bg-gray-100 cursor-pointer transition-colors"
          >
            <Ban className="w-3 h-3" /> Blacklist
          </button>
        </div>
      </div>

      {/* Email Thread */}
      <div className="p-5">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-1.5">
          <Mail className="w-3.5 h-3.5" /> Email Thread ({emails.length})
        </p>
        {emails.length === 0 ? (
          <p className="text-sm text-gray-400">No emails yet.</p>
        ) : (
          <div className="space-y-3">
            {emails.map((email) => (
              <div
                key={email.id}
                className={`rounded-xl p-4 border ${
                  email.direction === 'outbound'
                    ? 'bg-white border-gray-200/60'
                    : 'bg-orange-50/50 border-orange-200/60'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className={`text-xs font-medium ${
                    email.direction === 'outbound' ? 'text-gray-500' : 'text-orange-600'
                  }`}>
                    {email.direction === 'outbound' ? `Step ${email.sequence_step} \u2014 Sent` : 'Reply'}
                  </span>
                  <span className="text-xs text-gray-400 font-mono">
                    {email.sent_at ? new Date(email.sent_at).toLocaleString() : ''}
                  </span>
                </div>
                <p className="text-sm font-medium mb-1 text-gray-900">{email.subject}</p>
                <p className="text-sm leading-relaxed text-gray-500">
                  {email.body_text ? email.body_text.slice(0, 300) : ''}
                  {email.body_text && email.body_text.length > 300 ? '...' : ''}
                </p>
                {email.direction === 'outbound' && (
                  <div className="flex gap-2 mt-2.5">
                    {email.delivered_at && <Badge variant="success" size="sm">Delivered</Badge>}
                    {email.opened_at && <Badge variant="info" size="sm">Opened</Badge>}
                    {email.clicked_at && <Badge variant="warning" size="sm">Clicked</Badge>}
                    {email.bounced_at && <Badge variant="danger" size="sm">Bounced</Badge>}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- Scrape Jobs Tab ---------- */

function ScrapeJobsTab({ scrapeJobs }) {
  const columns = [
    { key: 'platform', label: 'Platform', render: (val) => <span className="text-gray-500 capitalize">{(val || '').replace('_', ' ')}</span> },
    { key: 'trade_type', label: 'Trade', render: (val) => <span className="text-gray-500 capitalize">{val}</span> },
    { key: 'city', label: 'Location', render: (_, row) => <span className="text-gray-900">{row.city}, {row.state_code}</span> },
    { key: 'status', label: 'Status', render: (val) => <Badge variant={JOB_STATUS_VARIANT[val] || 'neutral'} size="sm">{formatStatus(val)}</Badge> },
    { key: 'results_found', label: 'Found', align: 'right', render: (val) => <span className="font-mono">{val}</span> },
    { key: 'new_prospects_created', label: 'New', align: 'right', render: (val) => <span className="font-mono text-emerald-600">{val}</span> },
    { key: 'duplicates_skipped', label: 'Dupes', align: 'right', render: (val) => <span className="font-mono text-gray-400">{val}</span> },
    { key: 'api_cost_usd', label: 'Cost', align: 'right', render: (val) => <span className="font-mono">${(val ?? 0).toFixed(3)}</span> },
    { key: 'created_at', label: 'Date', render: (val) => <span className="text-gray-400">{val ? new Date(val).toLocaleDateString() : '\u2014'}</span> },
  ];

  return (
    <DataTable
      columns={columns}
      data={scrapeJobs}
      emptyMessage="No scrape jobs yet. Run your first scrape."
    />
  );
}

/* ---------- Status Tab ---------- */

function StatusTab({ workerStatus }) {
  if (!workerStatus) {
    return <p className="text-sm text-gray-400">Loading worker status...</p>;
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        {workerStatus.workers && Object.entries(workerStatus.workers).map(([name, info]) => (
          <div key={name} className="bg-white border border-gray-200/60 rounded-2xl p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <StatusDot color={HEALTH_DOT_MAP[info.health] || 'gray'} />
              <span className="text-sm font-medium capitalize text-gray-900">
                {name.replace(/_/g, ' ')}
              </span>
            </div>
            <p className="text-xs text-gray-400 font-mono">
              {info.health === 'unknown'
                ? 'No heartbeat'
                : info.last_heartbeat
                  ? `Last: ${new Date(info.last_heartbeat).toLocaleTimeString()}`
                  : 'N/A'}
            </p>
            <p className={`text-xs capitalize font-semibold mt-1 ${
              info.health === 'healthy' ? 'text-emerald-700'
              : info.health === 'warning' ? 'text-amber-700'
              : info.health === 'unhealthy' ? 'text-red-700'
              : 'text-gray-500'
            }`}>
              {info.health}
            </p>
          </div>
        ))}
      </div>
      {workerStatus.alerts && (
        <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Alerts</p>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600">Bounce Rate:</span>
            <span className={`text-sm font-mono font-medium ${
              workerStatus.alerts.bounce_rate_alert ? 'text-red-600' : 'text-emerald-600'
            }`}>
              {workerStatus.alerts.bounce_rate || 0}%
            </span>
            {workerStatus.alerts.bounce_rate_alert && (
              <Badge variant="danger" size="sm">HIGH</Badge>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Main Component ---------- */

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

  const [prospects, setProspects] = useState([]);
  const [prospectsTotal, setProspectsTotal] = useState(0);
  const [prospectsPage, setProspectsPage] = useState(1);
  const [prospectsFilter, setProspectsFilter] = useState({ status: '', trade_type: '', search: '' });
  const [selectedProspect, setSelectedProspect] = useState(null);
  const [prospectEmails, setProspectEmails] = useState([]);

  const [workerStatus, setWorkerStatus] = useState(null);
  const [error, setError] = useState(null);

  const fetchAll = async () => {
    try {
      setError(null);
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
      setError(e.message || 'Failed to load sales engine data. Please try again.');
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
      setConfig((c) => ({ ...c, is_active: !c.is_active }));
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
    if (!config) return;
    if (!newLocation.city || !newLocation.state) return;
    const locations = [...(config.target_locations || []), { ...newLocation }];
    setConfig((c) => ({ ...c, target_locations: locations }));
    setNewLocation({ city: '', state: '' });
  };

  const removeLocation = (idx) => {
    if (!config) return;
    const locations = (config.target_locations || []).filter((_, i) => i !== idx);
    setConfig((c) => ({ ...c, target_locations: locations }));
  };

  const toggleTradeType = (trade) => {
    if (!config) return;
    const types = config.target_trade_types || [];
    const updated = types.includes(trade) ? types.filter((t) => t !== trade) : [...types, trade];
    setConfig((c) => ({ ...c, target_trade_types: updated }));
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
    { id: 'metrics', label: 'Metrics' },
    { id: 'prospects', label: 'Prospects', count: prospectsTotal || undefined },
    { id: 'scraping', label: 'Scrape Jobs', count: scrapeJobs.length || undefined },
    { id: 'status', label: 'Status' },
    { id: 'settings', label: 'Settings' },
  ];

  if (loading) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <div className="h-8 w-48 rounded-lg bg-gray-100 animate-pulse mb-6" />
        <div className="h-64 bg-gray-100 rounded-2xl animate-pulse" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <PageHeader
        title="Sales Engine"
        actions={
          <div className="flex items-center gap-3">
            <button
              onClick={handleToggle}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-medium transition-all cursor-pointer ${
                config?.is_active
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/60'
                  : 'bg-gray-50 text-gray-500 border border-gray-200'
              }`}
            >
              <Zap className="w-3.5 h-3.5" />
              {config?.is_active ? 'Active' : 'Inactive'}
            </button>
            <button
              onClick={() => setShowScrapeForm(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer"
            >
              <Play className="w-4 h-4" />
              Run Scrape
            </button>
          </div>
        }
      />

      {error && (
        <div className="mb-4 flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-sm text-red-700">
          <span>{error}</span>
          <button
            onClick={() => { setLoading(true); fetchAll(); }}
            className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium text-red-700 bg-white border border-red-200 hover:bg-red-100 transition-colors cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      <ScrapeFormModal
        show={showScrapeForm}
        form={scrapeForm}
        onChange={setScrapeForm}
        onSubmit={handleScrape}
        onClose={() => setShowScrapeForm(false)}
        scraping={scraping}
      />

      <Tabs tabs={tabs} activeId={activeTab} onChange={setActiveTab} />

      {activeTab === 'metrics' && <MetricsTab metrics={metrics} />}

      {activeTab === 'prospects' && (
        <ProspectsTab
          prospects={prospects}
          prospectsTotal={prospectsTotal}
          prospectsPage={prospectsPage}
          prospectsFilter={prospectsFilter}
          onFilterChange={setProspectsFilter}
          onPageChange={setProspectsPage}
          selectedProspect={selectedProspect}
          prospectEmails={prospectEmails}
          onSelectProspect={handleSelectProspect}
          onCloseDetail={() => setSelectedProspect(null)}
          onDeleteProspect={handleDeleteProspect}
          onBlacklistProspect={handleBlacklistProspect}
          maxSequenceSteps={config?.max_sequence_steps}
        />
      )}

      {activeTab === 'scraping' && <ScrapeJobsTab scrapeJobs={scrapeJobs} />}

      {activeTab === 'status' && <StatusTab workerStatus={workerStatus} />}

      {activeTab === 'settings' && (
        <SalesEngineSettings
          config={config}
          onConfigChange={setConfig}
          newLocation={newLocation}
          onNewLocationChange={setNewLocation}
          onAddLocation={addLocation}
          onRemoveLocation={removeLocation}
          onToggleTradeType={toggleTradeType}
          onSave={handleSaveConfig}
          saving={saving}
        />
      )}
    </div>
  );
}
