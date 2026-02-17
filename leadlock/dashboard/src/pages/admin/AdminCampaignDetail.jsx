import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Send, ArrowLeft, Play, Pause, Plus, X, Users, Mail,
  Eye, MessageSquare, AlertTriangle, BarChart3, Settings, Layers,
  ChevronRight, Search,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../../api/client';

const STATUS_BADGE = {
  draft: 'bg-gray-50 text-gray-700 border border-gray-200',
  active: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  paused: 'bg-amber-50 text-amber-700 border border-amber-100',
  completed: 'bg-blue-50 text-blue-700 border border-blue-100',
};

const PROSPECT_STATUS_BADGE = {
  cold: 'bg-gray-100 text-gray-600',
  contacted: 'bg-blue-50 text-blue-600',
  demo_scheduled: 'bg-violet-50 text-violet-600',
  won: 'bg-emerald-50 text-emerald-600',
  lost: 'bg-red-50 text-red-600',
};

const TABS = [
  { key: 'sequence', label: 'Sequence', icon: Layers },
  { key: 'prospects', label: 'Prospects', icon: Users },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
  { key: 'settings', label: 'Settings', icon: Settings },
];

function MetricCard({ label, value, icon: Icon, color = 'gray' }) {
  const colors = {
    gray: { bg: 'bg-gray-50', text: 'text-gray-600' },
    blue: { bg: 'bg-blue-50', text: 'text-blue-600' },
    emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
    violet: { bg: 'bg-violet-50', text: 'text-violet-600' },
    red: { bg: 'bg-red-50', text: 'text-red-600' },
  };
  const c = colors[color] || colors.gray;
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${c.bg}`}>
          <Icon className={`w-3.5 h-3.5 ${c.text}`} />
        </div>
        <span className="text-[11px] font-medium uppercase tracking-wider text-gray-400">{label}</span>
      </div>
      <p className="text-xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

export default function AdminCampaignDetail() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const [campaign, setCampaign] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('sequence');

  // Sequence state
  const [steps, setSteps] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [saving, setSaving] = useState(false);

  // Prospects state
  const [prospects, setProspects] = useState([]);
  const [prospectsTotal, setProspectsTotal] = useState(0);
  const [prospectsPage, setProspectsPage] = useState(1);
  const [prospectsSearch, setProspectsSearch] = useState('');
  const [showAssign, setShowAssign] = useState(false);
  const [assignFilters, setAssignFilters] = useState({ trade_type: '', city: '', state: '', status: 'cold' });

  // Analytics state
  const [metrics, setMetrics] = useState(null);

  // Settings state
  const [settingsForm, setSettingsForm] = useState(null);

  const loadCampaign = useCallback(async () => {
    try {
      const data = await api.getCampaignDetail(campaignId);
      setCampaign(data);
      setSteps(data.sequence_steps || []);
      setSettingsForm({
        name: data.name,
        description: data.description || '',
        daily_limit: data.daily_limit,
        target_trades: (data.target_trades || []).join(', '),
        target_locations: (data.target_locations || []).map(l =>
          typeof l === 'string' ? l : `${l.city || ''}, ${l.state || ''}`
        ).join('; '),
      });
    } catch (err) {
      console.error('Failed to load campaign:', err);
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  const loadProspects = useCallback(async () => {
    try {
      const params = { page: prospectsPage, per_page: 25 };
      if (prospectsSearch) params.search = prospectsSearch;
      const data = await api.getCampaignProspects(campaignId, params);
      setProspects(data.prospects || []);
      setProspectsTotal(data.total || 0);
    } catch {
      // endpoint may not be ready
    }
  }, [campaignId, prospectsPage, prospectsSearch]);

  const loadMetrics = useCallback(async () => {
    try {
      const data = await api.getCampaignMetrics(campaignId);
      setMetrics(data);
    } catch {
      // endpoint may not be ready
    }
  }, [campaignId]);

  const loadTemplates = useCallback(async () => {
    try {
      const data = await api.getTemplates();
      setTemplates(data.templates || []);
    } catch {
      // templates endpoint may not be ready
    }
  }, []);

  useEffect(() => { loadCampaign(); loadTemplates(); }, [loadCampaign, loadTemplates]);
  useEffect(() => { if (activeTab === 'prospects') loadProspects(); }, [activeTab, loadProspects]);
  useEffect(() => { if (activeTab === 'analytics') loadMetrics(); }, [activeTab, loadMetrics]);

  const handleActivate = async () => {
    try {
      await api.activateCampaign(campaignId);
      loadCampaign();
    } catch (err) {
      alert(err.message || 'Failed to activate campaign');
    }
  };

  const handlePauseResume = async () => {
    try {
      if (campaign.status === 'active') {
        await api.pauseCampaign(campaignId);
      } else {
        await api.resumeCampaign(campaignId);
      }
      loadCampaign();
    } catch (err) {
      console.error('Toggle failed:', err);
    }
  };

  const handleSaveSequence = async () => {
    setSaving(true);
    try {
      await api.updateCampaign(campaignId, { sequence_steps: steps });
      loadCampaign();
    } catch (err) {
      console.error('Save failed:', err);
    } finally {
      setSaving(false);
    }
  };

  const addStep = () => {
    const newStep = {
      step: steps.length + 1,
      channel: 'email',
      delay_hours: steps.length === 0 ? 0 : 48,
      template_id: null,
    };
    setSteps([...steps, newStep]);
  };

  const removeStep = (index) => {
    const updated = steps
      .filter((_, i) => i !== index)
      .map((s, i) => ({ ...s, step: i + 1 }));
    setSteps(updated);
  };

  const updateStep = (index, field, value) => {
    setSteps(steps.map((s, i) =>
      i === index ? { ...s, [field]: value } : s
    ));
  };

  const handleAssign = async () => {
    try {
      const filters = {};
      if (assignFilters.trade_type) filters.trade_type = assignFilters.trade_type;
      if (assignFilters.city) filters.city = assignFilters.city;
      if (assignFilters.state) filters.state = assignFilters.state;
      if (assignFilters.status) filters.status = assignFilters.status;
      const result = await api.assignProspects(campaignId, { filters });
      setShowAssign(false);
      loadProspects();
      loadCampaign();
      alert(`Assigned ${result.count} prospects`);
    } catch (err) {
      console.error('Assignment failed:', err);
    }
  };

  const handleSaveSettings = async () => {
    try {
      const trades = settingsForm.target_trades
        .split(',')
        .map(t => t.trim())
        .filter(Boolean);
      const locations = settingsForm.target_locations
        .split(';')
        .map(l => l.trim())
        .filter(Boolean)
        .map(l => {
          const parts = l.split(',').map(p => p.trim());
          return parts.length === 2 ? { city: parts[0], state: parts[1] } : l;
        });
      await api.updateCampaign(campaignId, {
        name: settingsForm.name,
        description: settingsForm.description,
        daily_limit: parseInt(settingsForm.daily_limit) || 25,
        target_trades: trades,
        target_locations: locations,
      });
      loadCampaign();
    } catch (err) {
      console.error('Settings save failed:', err);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Delete this campaign? This cannot be undone.')) return;
    try {
      await api.updateCampaign(campaignId, { status: 'completed' });
      navigate('/campaigns');
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-violet-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-gray-500">Campaign not found</p>
      </div>
    );
  }

  const totalSent = campaign.emails?.sent || campaign.total_sent || 0;
  const openRate = campaign.emails?.open_rate || (totalSent ? ((campaign.total_opened || 0) / totalSent * 100).toFixed(1) : '0');
  const replyRate = campaign.emails?.reply_rate || (totalSent ? ((campaign.total_replied || 0) / totalSent * 100).toFixed(1) : '0');
  const bounceRate = campaign.emails?.bounce_rate || '0';

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/campaigns')}
          className="p-2 rounded-lg bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4 text-gray-500" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-gray-900">{campaign.name}</h1>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium capitalize ${STATUS_BADGE[campaign.status] || STATUS_BADGE.draft}`}>
              {campaign.status}
            </span>
          </div>
          {campaign.description && (
            <p className="text-xs text-gray-400 mt-0.5">{campaign.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {campaign.status === 'draft' && (
            <button
              onClick={handleActivate}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 transition-colors cursor-pointer"
            >
              <Play className="w-3.5 h-3.5" /> Activate
            </button>
          )}
          {(campaign.status === 'active' || campaign.status === 'paused') && (
            <button
              onClick={handlePauseResume}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                campaign.status === 'active'
                  ? 'text-amber-700 bg-amber-50 border border-amber-200 hover:bg-amber-100'
                  : 'text-emerald-700 bg-emerald-50 border border-emerald-200 hover:bg-emerald-100'
              }`}
            >
              {campaign.status === 'active' ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              {campaign.status === 'active' ? 'Pause' : 'Resume'}
            </button>
          )}
        </div>
      </div>

      {/* Metrics cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
        <MetricCard label="Prospects" value={campaign.prospects?.total || 0} icon={Users} color="blue" />
        <MetricCard label="Sent" value={totalSent} icon={Mail} color="violet" />
        <MetricCard label="Open Rate" value={`${openRate}%`} icon={Eye} color="emerald" />
        <MetricCard label="Reply Rate" value={`${replyRate}%`} icon={MessageSquare} color="violet" />
        <MetricCard label="Bounce Rate" value={`${bounceRate}%`} icon={AlertTriangle} color="red" />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 overflow-x-auto">
        {TABS.map(({ key, label, icon: Icon }) => (
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

      {/* Tab Content */}

      {/* Sequence Tab */}
      {activeTab === 'sequence' && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-900">Sequence Steps</h2>
            <button
              onClick={handleSaveSequence}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-violet-600 hover:bg-violet-700 disabled:opacity-50 transition-colors cursor-pointer"
            >
              {saving ? 'Saving...' : 'Save Sequence'}
            </button>
          </div>

          <div className="space-y-3">
            {steps.map((step, i) => (
              <div key={i} className="flex items-center gap-3 bg-gray-50 border border-gray-100 rounded-lg p-3">
                <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-violet-100 text-violet-700 text-xs font-bold">
                  {step.step}
                </div>
                <ChevronRight className="w-3 h-3 text-gray-400" />

                <div className="flex items-center gap-2 flex-1">
                  <div>
                    <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1">Delay (hours)</label>
                    <input
                      type="number"
                      min="0"
                      value={step.delay_hours}
                      onChange={e => updateStep(i, 'delay_hours', parseInt(e.target.value) || 0)}
                      className="w-20 px-2 py-1 bg-white border border-gray-200 rounded-md text-xs text-gray-900 outline-none focus:border-violet-500 transition-shadow"
                    />
                  </div>

                  <div className="flex-1">
                    <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1">Template</label>
                    <select
                      value={step.template_id || ''}
                      onChange={e => updateStep(i, 'template_id', e.target.value || null)}
                      className="w-full px-2 py-1 bg-white border border-gray-200 rounded-md text-xs text-gray-900 outline-none focus:border-violet-500 cursor-pointer"
                    >
                      <option value="">AI Generated</option>
                      {templates.map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <button
                  onClick={() => removeStep(i)}
                  className="p-1.5 rounded-lg hover:bg-red-50 transition-colors cursor-pointer"
                >
                  <X className="w-3.5 h-3.5 text-gray-400 hover:text-red-500" />
                </button>
              </div>
            ))}
          </div>

          <button
            onClick={addStep}
            className="flex items-center gap-1.5 mt-3 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 bg-white border border-gray-200 border-dashed hover:border-violet-300 hover:text-violet-600 transition-colors cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" /> Add Step
          </button>
        </div>
      )}

      {/* Prospects Tab */}
      {activeTab === 'prospects' && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm">
          <div className="flex items-center justify-between p-4 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search prospects..."
                  value={prospectsSearch}
                  onChange={e => { setProspectsSearch(e.target.value); setProspectsPage(1); }}
                  className="pl-8 pr-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs outline-none focus:border-violet-500 w-48"
                />
              </div>
              <span className="text-[11px] text-gray-400">{prospectsTotal} prospects</span>
            </div>
            <button
              onClick={() => setShowAssign(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-violet-700 bg-violet-50 border border-violet-200 hover:bg-violet-100 transition-colors cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" /> Assign Prospects
            </button>
          </div>

          {/* Assign modal */}
          {showAssign && (
            <div className="p-4 bg-violet-50/50 border-b border-violet-100">
              <h3 className="text-xs font-semibold text-gray-900 mb-3">Assign Unbound Prospects</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                <div>
                  <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1">Trade</label>
                  <input
                    type="text"
                    value={assignFilters.trade_type}
                    onChange={e => setAssignFilters({ ...assignFilters, trade_type: e.target.value })}
                    className="w-full px-2 py-1.5 bg-white border border-gray-200 rounded-md text-xs outline-none focus:border-violet-500"
                    placeholder="e.g. hvac"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1">City</label>
                  <input
                    type="text"
                    value={assignFilters.city}
                    onChange={e => setAssignFilters({ ...assignFilters, city: e.target.value })}
                    className="w-full px-2 py-1.5 bg-white border border-gray-200 rounded-md text-xs outline-none focus:border-violet-500"
                    placeholder="e.g. Austin"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1">State</label>
                  <input
                    type="text"
                    value={assignFilters.state}
                    onChange={e => setAssignFilters({ ...assignFilters, state: e.target.value })}
                    className="w-full px-2 py-1.5 bg-white border border-gray-200 rounded-md text-xs outline-none focus:border-violet-500"
                    placeholder="e.g. TX"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1">Status</label>
                  <select
                    value={assignFilters.status}
                    onChange={e => setAssignFilters({ ...assignFilters, status: e.target.value })}
                    className="w-full px-2 py-1.5 bg-white border border-gray-200 rounded-md text-xs outline-none focus:border-violet-500 cursor-pointer"
                  >
                    <option value="cold">Cold</option>
                    <option value="contacted">Contacted</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={handleAssign} className="px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-violet-600 hover:bg-violet-700 cursor-pointer">
                  Assign Matching
                </button>
                <button onClick={() => setShowAssign(false)} className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 cursor-pointer">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Prospects table */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 px-4 py-2">Name</th>
                  <th className="text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 px-4 py-2">Company</th>
                  <th className="text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 px-4 py-2">Email</th>
                  <th className="text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 px-4 py-2">Step</th>
                  <th className="text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 px-4 py-2">Status</th>
                  <th className="text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 px-4 py-2">Last Sent</th>
                  <th className="text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 px-4 py-2">Activity</th>
                </tr>
              </thead>
              <tbody>
                {prospects.map(p => (
                  <tr key={p.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                    <td className="px-4 py-2.5 text-xs font-medium text-gray-900">{p.prospect_name}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-500">{p.prospect_company || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-500 font-mono">{p.prospect_email || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-600">{p.outreach_sequence_step}</td>
                    <td className="px-4 py-2.5">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium capitalize ${PROSPECT_STATUS_BADGE[p.status] || 'bg-gray-100 text-gray-600'}`}>
                        {p.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-400">
                      {p.last_email_sent_at ? new Date(p.last_email_sent_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        {p.last_email_opened_at && <Eye className="w-3 h-3 text-emerald-500" />}
                        {p.last_email_replied_at && <MessageSquare className="w-3 h-3 text-violet-500" />}
                        {!p.last_email_opened_at && !p.last_email_replied_at && <span className="text-[10px] text-gray-300">—</span>}
                      </div>
                    </td>
                  </tr>
                ))}
                {prospects.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center py-8 text-xs text-gray-400">
                      No prospects assigned to this campaign yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {prospectsTotal > 25 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
              <span className="text-[11px] text-gray-400">
                Page {prospectsPage} of {Math.ceil(prospectsTotal / 25)}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => setProspectsPage(Math.max(1, prospectsPage - 1))}
                  disabled={prospectsPage === 1}
                  className="px-2 py-1 rounded text-xs text-gray-500 bg-white border border-gray-200 disabled:opacity-40 cursor-pointer"
                >
                  Prev
                </button>
                <button
                  onClick={() => setProspectsPage(prospectsPage + 1)}
                  disabled={prospectsPage >= Math.ceil(prospectsTotal / 25)}
                  className="px-2 py-1 rounded text-xs text-gray-500 bg-white border border-gray-200 disabled:opacity-40 cursor-pointer"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Analytics Tab */}
      {activeTab === 'analytics' && metrics && (
        <div className="space-y-5">
          {/* Step performance chart */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Step Performance</h2>
            {metrics.step_performance?.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={metrics.step_performance}>
                  <XAxis dataKey="step" tick={{ fontSize: 11 }} tickFormatter={v => `Step ${v}`} />
                  <YAxis tick={{ fontSize: 11 }} unit="%" />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                    formatter={(value, name) => [`${value}%`, name === 'open_rate' ? 'Open Rate' : 'Reply Rate']}
                  />
                  <Bar dataKey="open_rate" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="open_rate" />
                  <Bar dataKey="reply_rate" fill="#06b6d4" radius={[4, 4, 0, 0]} name="reply_rate" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-gray-400 text-center py-8">No step data yet — send some emails first.</p>
            )}
          </div>

          {/* Daily sends chart */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Daily Send Volume (14 days)</h2>
            {metrics.daily_sends?.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={metrics.daily_sends}>
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    tickFormatter={v => v ? new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}
                  />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                    labelFormatter={v => v ? new Date(v).toLocaleDateString() : ''}
                  />
                  <Bar dataKey="sent" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-gray-400 text-center py-8">No daily data yet.</p>
            )}
          </div>

          {/* Campaign funnel */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Campaign Funnel</h2>
            {metrics.funnel ? (
              <div className="space-y-2">
                {[
                  { key: 'cold', label: 'Cold', color: 'bg-gray-400' },
                  { key: 'contacted', label: 'Contacted', color: 'bg-blue-500' },
                  { key: 'demo_scheduled', label: 'Demo Scheduled', color: 'bg-violet-500' },
                  { key: 'won', label: 'Won', color: 'bg-emerald-500' },
                  { key: 'lost', label: 'Lost', color: 'bg-red-400' },
                ].map(({ key, label, color }) => {
                  const count = metrics.funnel[key] || 0;
                  const total = Object.values(metrics.funnel).reduce((a, b) => a + b, 0) || 1;
                  const pct = (count / total * 100).toFixed(0);
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 w-28">{label}</span>
                      <div className="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden">
                        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs font-medium text-gray-700 w-12 text-right">{count}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-gray-400 text-center py-8">No funnel data yet.</p>
            )}
          </div>
        </div>
      )}

      {activeTab === 'analytics' && !metrics && (
        <div className="flex items-center justify-center h-32">
          <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && settingsForm && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Campaign Settings</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1.5">Name</label>
              <input
                type="text"
                value={settingsForm.name}
                onChange={e => setSettingsForm({ ...settingsForm, name: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-shadow"
              />
            </div>
            <div>
              <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1.5">Description</label>
              <textarea
                value={settingsForm.description}
                onChange={e => setSettingsForm({ ...settingsForm, description: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-shadow h-20 resize-none"
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1.5">Daily Limit</label>
                <input
                  type="number"
                  value={settingsForm.daily_limit}
                  onChange={e => setSettingsForm({ ...settingsForm, daily_limit: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-shadow"
                />
              </div>
              <div>
                <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1.5">Target Trades (comma-separated)</label>
                <input
                  type="text"
                  value={settingsForm.target_trades}
                  onChange={e => setSettingsForm({ ...settingsForm, target_trades: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-shadow"
                  placeholder="hvac, plumbing, roofing"
                />
              </div>
              <div>
                <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-400 mb-1.5">Target Locations (City, ST; ...)</label>
                <input
                  type="text"
                  value={settingsForm.target_locations}
                  onChange={e => setSettingsForm({ ...settingsForm, target_locations: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100 transition-shadow"
                  placeholder="Austin, TX; Dallas, TX"
                />
              </div>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleSaveSettings}
                className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 transition-colors cursor-pointer"
              >
                Save Settings
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 rounded-lg text-sm font-medium text-red-600 bg-white border border-red-200 hover:bg-red-50 transition-colors cursor-pointer"
              >
                Delete Campaign
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
