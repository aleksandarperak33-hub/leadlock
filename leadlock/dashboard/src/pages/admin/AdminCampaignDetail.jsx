import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Play, Pause, Plus, X, Users, Mail,
  Eye, MessageSquare, AlertTriangle, Pencil,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../../api/client';
import PageHeader from '../../components/ui/PageHeader';
import Badge from '../../components/ui/Badge';
import Tabs from '../../components/ui/Tabs';
import StatCard from '../../components/ui/StatCard';
import SearchInput from '../../components/ui/SearchInput';

const STATUS_VARIANT = {
  draft: 'neutral',
  active: 'success',
  paused: 'warning',
  completed: 'neutral',
};

const PROSPECT_STATUS_VARIANT = {
  cold: 'neutral',
  contacted: 'info',
  demo_scheduled: 'warning',
  won: 'success',
  lost: 'danger',
};

const TAB_ITEMS = [
  { id: 'sequence', label: 'Sequence' },
  { id: 'prospects', label: 'Prospects' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'settings', label: 'Settings' },
];

const CHART_TOOLTIP_STYLE = {
  fontSize: 12,
  borderRadius: 12,
  border: '1px solid rgba(229,231,235,0.6)',
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
};

const FUNNEL_STAGES = [
  { key: 'cold', label: 'Cold', color: 'bg-gray-400' },
  { key: 'contacted', label: 'Contacted', color: 'bg-blue-500' },
  { key: 'demo_scheduled', label: 'Demo Scheduled', color: 'bg-orange-500' },
  { key: 'won', label: 'Won', color: 'bg-emerald-500' },
  { key: 'lost', label: 'Lost', color: 'bg-red-400' },
];

function SequenceTab({ steps, templates, saving, onUpdate, onAdd, onRemove, onSave }) {
  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm p-6">
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-lg font-semibold text-gray-900">Sequence Steps</h2>
        <button
          onClick={onSave}
          disabled={saving}
          className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 disabled:opacity-50 transition-colors cursor-pointer"
        >
          {saving ? 'Saving...' : 'Save Sequence'}
        </button>
      </div>

      <div className="relative">
        {steps.length > 1 && (
          <div className="absolute left-[19px] top-6 bottom-6 w-px bg-gray-200" />
        )}

        <div className="space-y-4">
          {steps.map((step, i) => (
            <div key={i} className="relative flex items-start gap-4">
              <div className="relative z-10 flex items-center justify-center w-10 h-10 rounded-xl bg-orange-50 border border-orange-200/60 shrink-0">
                <span className="text-xs font-bold text-orange-500 font-mono">
                  {step.step}
                </span>
              </div>
              <div className="flex-1 bg-white border border-gray-200/60 rounded-xl p-5">
                <div className="flex items-center gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      Delay (hours)
                    </label>
                    <input
                      type="number"
                      min="0"
                      value={step.delay_hours}
                      onChange={(e) => onUpdate(i, 'delay_hours', parseInt(e.target.value) || 0)}
                      className="w-24 px-3 py-2 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 font-mono outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      Template
                    </label>
                    <select
                      value={step.template_id || ''}
                      onChange={(e) => onUpdate(i, 'template_id', e.target.value || null)}
                      className="w-full px-3 py-2 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 cursor-pointer"
                    >
                      <option value="">AI Generated</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={() => onRemove(i)}
                    className="p-2 rounded-xl hover:bg-red-50 transition-colors cursor-pointer mt-5"
                  >
                    <X className="w-4 h-4 text-gray-400 hover:text-red-500" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={onAdd}
        className="flex items-center gap-1.5 mt-4 px-4 py-2 rounded-xl text-sm font-medium text-gray-500 border border-gray-200 border-dashed hover:border-orange-300 hover:text-orange-600 transition-colors cursor-pointer"
      >
        <Plus className="w-4 h-4" /> Add Step
      </button>
    </div>
  );
}

function AssignModal({ filters, onChange, onAssign, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b border-gray-200/60">
          <h3 className="text-lg font-semibold text-gray-900">Assign Prospects</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 cursor-pointer">
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          {[
            { key: 'trade_type', label: 'Trade', placeholder: 'e.g. hvac' },
            { key: 'city', label: 'City', placeholder: 'e.g. Austin' },
            { key: 'state', label: 'State', placeholder: 'e.g. TX' },
          ].map(({ key, label, placeholder }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">{label}</label>
              <input
                type="text"
                value={filters[key]}
                onChange={(e) => onChange({ ...filters, [key]: e.target.value })}
                className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100"
                placeholder={placeholder}
              />
            </div>
          ))}
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Status</label>
            <select
              value={filters.status}
              onChange={(e) => onChange({ ...filters, status: e.target.value })}
              className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm outline-none focus:border-orange-500 cursor-pointer"
            >
              <option value="cold">Cold</option>
              <option value="contacted">Contacted</option>
            </select>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-200/60">
          <button onClick={onClose} className="px-4 py-2 rounded-xl text-sm font-medium text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 cursor-pointer">Cancel</button>
          <button onClick={onAssign} className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 cursor-pointer">Assign Matching</button>
        </div>
      </div>
    </div>
  );
}

function ProspectsTab({ prospects, total, page, search, showAssign, assignFilters, onSearch, onPage, onShowAssign, onAssignChange, onAssign, onCloseAssign }) {
  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm overflow-hidden">
      <div className="flex items-center justify-between p-5 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="w-56">
            <SearchInput value={search} onChange={onSearch} placeholder="Search prospects..." />
          </div>
          <span className="text-xs text-gray-400">{total} prospects</span>
        </div>
        <button
          onClick={onShowAssign}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium text-orange-600 bg-orange-50 border border-orange-200/60 hover:bg-orange-100 transition-colors cursor-pointer"
        >
          <Plus className="w-4 h-4" /> Assign Prospects
        </button>
      </div>

      {showAssign && (
        <AssignModal
          filters={assignFilters}
          onChange={onAssignChange}
          onAssign={onAssign}
          onClose={onCloseAssign}
        />
      )}

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50/80 border-b border-gray-200/60">
              {['Name', 'Company', 'Email', 'Step', 'Status', 'Last Sent', 'Activity'].map((h) => (
                <th key={h} className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {prospects.map((p) => (
              <tr key={p.id} className="border-b border-gray-100 hover:bg-gray-50/50 transition-colors">
                <td className="px-4 py-3.5 text-sm font-medium text-gray-900">{p.prospect_name}</td>
                <td className="px-4 py-3.5 text-sm text-gray-500">{p.prospect_company || '--'}</td>
                <td className="px-4 py-3.5 text-sm text-gray-500 font-mono">{p.prospect_email || '--'}</td>
                <td className="px-4 py-3.5 text-sm text-gray-600 font-mono">{p.outreach_sequence_step}</td>
                <td className="px-4 py-3.5">
                  <Badge variant={PROSPECT_STATUS_VARIANT[p.status] || 'neutral'}>{p.status}</Badge>
                </td>
                <td className="px-4 py-3.5 text-sm text-gray-400 font-mono">
                  {p.last_email_sent_at ? new Date(p.last_email_sent_at).toLocaleDateString() : '--'}
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-1.5">
                    {p.last_email_opened_at && <Eye className="w-3.5 h-3.5 text-emerald-500" />}
                    {p.last_email_replied_at && <MessageSquare className="w-3.5 h-3.5 text-orange-500" />}
                    {!p.last_email_opened_at && !p.last_email_replied_at && <span className="text-xs text-gray-300">--</span>}
                  </div>
                </td>
              </tr>
            ))}
            {prospects.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center py-12 text-sm text-gray-400">
                  No prospects assigned to this campaign yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {total > 25 && (
        <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100">
          <span className="text-xs text-gray-400">Page {page} of {Math.ceil(total / 25)}</span>
          <div className="flex gap-1.5">
            <button onClick={() => onPage(Math.max(1, page - 1))} disabled={page === 1} className="px-3 py-1.5 rounded-lg text-xs text-gray-500 bg-white border border-gray-200 disabled:opacity-40 cursor-pointer">Prev</button>
            <button onClick={() => onPage(page + 1)} disabled={page >= Math.ceil(total / 25)} className="px-3 py-1.5 rounded-lg text-xs text-gray-500 bg-white border border-gray-200 disabled:opacity-40 cursor-pointer">Next</button>
          </div>
        </div>
      )}
    </div>
  );
}

function AnalyticsTab({ metrics }) {
  if (!metrics) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const total = metrics.funnel ? Object.values(metrics.funnel).reduce((a, b) => a + b, 0) || 1 : 1;

  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Step Performance</h2>
        {metrics.step_performance?.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={metrics.step_performance}>
              <XAxis dataKey="step" tick={{ fontSize: 11 }} tickFormatter={(v) => `Step ${v}`} />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} formatter={(value, name) => [`${value}%`, name === 'open_rate' ? 'Open Rate' : 'Reply Rate']} />
              <Bar dataKey="open_rate" fill="#f97316" radius={[6, 6, 0, 0]} name="open_rate" />
              <Bar dataKey="reply_rate" fill="#06b6d4" radius={[6, 6, 0, 0]} name="reply_rate" />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-gray-400 text-center py-12">No step data yet -- send some emails first.</p>
        )}
      </div>

      <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Daily Send Volume (14 days)</h2>
        {metrics.daily_sends?.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={metrics.daily_sends}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v ? new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelFormatter={(v) => v ? new Date(v).toLocaleDateString() : ''} />
              <Bar dataKey="sent" fill="#f97316" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-gray-400 text-center py-12">No daily data yet.</p>
        )}
      </div>

      <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Campaign Funnel</h2>
        {metrics.funnel ? (
          <div className="space-y-3">
            {FUNNEL_STAGES.map(({ key, label, color }) => {
              const count = metrics.funnel[key] || 0;
              const pct = (count / total * 100).toFixed(0);
              return (
                <div key={key} className="flex items-center gap-3">
                  <span className="text-sm text-gray-700 w-32 shrink-0">{label}</span>
                  <div className="flex-1 h-3 bg-orange-100 rounded-full overflow-hidden">
                    <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-sm font-mono text-gray-900 w-16 text-right">{count}</span>
                  <span className="text-xs text-gray-400 w-10 text-right font-mono">{pct}%</span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-gray-400 text-center py-12">No funnel data yet.</p>
        )}
      </div>
    </div>
  );
}

function SettingsTab({ form, onChange, onSave, onDelete }) {
  if (!form) return null;

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-6">Campaign Settings</h2>
      <div className="space-y-5">
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Name</label>
          <input type="text" value={form.name} onChange={(e) => onChange({ ...form, name: e.target.value })} className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Description</label>
          <textarea value={form.description} onChange={(e) => onChange({ ...form, description: e.target.value })} className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow h-20 resize-none" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Daily Limit</label>
            <input type="number" value={form.daily_limit} onChange={(e) => onChange({ ...form, daily_limit: parseInt(e.target.value) || 0 })} className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 font-mono outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Target Trades (comma-separated)</label>
            <input type="text" value={form.target_trades} onChange={(e) => onChange({ ...form, target_trades: e.target.value })} className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow" placeholder="hvac, plumbing, roofing" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Target Locations (City, ST; ...)</label>
            <input type="text" value={form.target_locations} onChange={(e) => onChange({ ...form, target_locations: e.target.value })} className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow" placeholder="Austin, TX; Dallas, TX" />
          </div>
        </div>
        <div className="flex items-center gap-3 pt-3 border-t border-gray-100">
          <button onClick={onSave} className="px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer">Save Settings</button>
          <button onClick={onDelete} className="px-4 py-2.5 rounded-xl text-sm font-medium text-red-600 bg-white border border-red-200 hover:bg-red-50 transition-colors cursor-pointer">Delete Campaign</button>
        </div>
      </div>
    </div>
  );
}

export default function AdminCampaignDetail() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const [campaign, setCampaign] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('sequence');

  const [steps, setSteps] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [saving, setSaving] = useState(false);

  const [prospects, setProspects] = useState([]);
  const [prospectsTotal, setProspectsTotal] = useState(0);
  const [prospectsPage, setProspectsPage] = useState(1);
  const [prospectsSearch, setProspectsSearch] = useState('');
  const [showAssign, setShowAssign] = useState(false);
  const [assignFilters, setAssignFilters] = useState({ trade_type: '', city: '', state: '', status: 'cold' });

  const [metrics, setMetrics] = useState(null);
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
        target_locations: (data.target_locations || []).map((l) =>
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
    } catch { /* endpoint may not be ready */ }
  }, [campaignId, prospectsPage, prospectsSearch]);

  const loadMetrics = useCallback(async () => {
    try {
      const data = await api.getCampaignMetrics(campaignId);
      setMetrics(data);
    } catch { /* endpoint may not be ready */ }
  }, [campaignId]);

  const loadTemplates = useCallback(async () => {
    try {
      const data = await api.getTemplates();
      setTemplates(data.templates || []);
    } catch { /* templates endpoint may not be ready */ }
  }, []);

  useEffect(() => { loadCampaign(); loadTemplates(); }, [loadCampaign, loadTemplates]);
  useEffect(() => { if (activeTab === 'prospects') loadProspects(); }, [activeTab, loadProspects]);
  useEffect(() => { if (activeTab === 'analytics') loadMetrics(); }, [activeTab, loadMetrics]);

  const handleActivate = async () => {
    try { await api.activateCampaign(campaignId); loadCampaign(); }
    catch (err) { alert(err.message || 'Failed to activate campaign'); }
  };

  const handlePauseResume = async () => {
    try {
      if (campaign.status === 'active') { await api.pauseCampaign(campaignId); }
      else { await api.resumeCampaign(campaignId); }
      loadCampaign();
    } catch (err) { console.error('Toggle failed:', err); }
  };

  const handleSaveSequence = async () => {
    setSaving(true);
    try { await api.updateCampaign(campaignId, { sequence_steps: steps }); loadCampaign(); }
    catch (err) { console.error('Save failed:', err); }
    finally { setSaving(false); }
  };

  const addStep = () => {
    const newStep = { step: steps.length + 1, channel: 'email', delay_hours: steps.length === 0 ? 0 : 48, template_id: null };
    setSteps([...steps, newStep]);
  };

  const removeStep = (index) => {
    setSteps(steps.filter((_, i) => i !== index).map((s, i) => ({ ...s, step: i + 1 })));
  };

  const updateStep = (index, field, value) => {
    setSteps(steps.map((s, i) => i === index ? { ...s, [field]: value } : s));
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
    } catch (err) { console.error('Assignment failed:', err); }
  };

  const handleSaveSettings = async () => {
    try {
      const trades = settingsForm.target_trades.split(',').map((t) => t.trim()).filter(Boolean);
      const locations = settingsForm.target_locations.split(';').map((l) => l.trim()).filter(Boolean).map((l) => {
        const parts = l.split(',').map((p) => p.trim());
        return parts.length === 2 ? { city: parts[0], state: parts[1] } : l;
      });
      await api.updateCampaign(campaignId, { name: settingsForm.name, description: settingsForm.description, daily_limit: parseInt(settingsForm.daily_limit) || 25, target_trades: trades, target_locations: locations });
      loadCampaign();
    } catch (err) { console.error('Settings save failed:', err); }
  };

  const handleDelete = async () => {
    if (!confirm('Delete this campaign? This cannot be undone.')) return;
    try { await api.updateCampaign(campaignId, { status: 'completed' }); navigate('/campaigns'); }
    catch (err) { console.error('Delete failed:', err); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
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
  const openRate = campaign.emails?.open_rate ?? (totalSent ? ((campaign.total_opened || 0) / totalSent * 100).toFixed(1) : '0');
  const replyRate = campaign.emails?.reply_rate ?? (totalSent ? ((campaign.total_replied || 0) / totalSent * 100).toFixed(1) : '0');
  const bounceRate = campaign.emails?.bounce_rate ?? '0';

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <div className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate('/campaigns')} className="p-2 rounded-xl bg-white border border-gray-200/60 hover:bg-gray-50 transition-colors cursor-pointer">
          <ArrowLeft className="w-4 h-4 text-gray-500" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-semibold tracking-tight text-gray-900">{campaign.name}</h1>
            <Badge variant={STATUS_VARIANT[campaign.status] || 'neutral'}>{campaign.status}</Badge>
          </div>
          {campaign.description && <p className="text-sm text-gray-500 mt-1">{campaign.description}</p>}
        </div>
        <div className="flex items-center gap-2">
          {campaign.status === 'draft' && (
            <button onClick={handleActivate} className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium text-white bg-emerald-500 hover:bg-emerald-600 transition-colors cursor-pointer">
              <Play className="w-3.5 h-3.5" /> Activate
            </button>
          )}
          {(campaign.status === 'active' || campaign.status === 'paused') && (
            <button onClick={handlePauseResume} className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-colors cursor-pointer ${campaign.status === 'active' ? 'text-amber-700 bg-amber-50 border border-amber-200/60 hover:bg-amber-100' : 'text-emerald-700 bg-emerald-50 border border-emerald-200/60 hover:bg-emerald-100'}`}>
              {campaign.status === 'active' ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              {campaign.status === 'active' ? 'Pause' : 'Resume'}
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <StatCard label="Prospects" value={campaign.prospect_count || 0} icon={Users} color="brand" />
        <StatCard label="Sent" value={totalSent} icon={Mail} color="brand" />
        <StatCard label="Open Rate" value={`${openRate}%`} icon={Eye} color="green" />
        <StatCard label="Reply Rate" value={`${replyRate}%`} icon={MessageSquare} color="brand" />
        <StatCard label="Bounce Rate" value={`${bounceRate}%`} icon={AlertTriangle} color="red" />
      </div>

      <Tabs tabs={TAB_ITEMS} activeId={activeTab} onChange={setActiveTab} />

      {activeTab === 'sequence' && (
        <SequenceTab steps={steps} templates={templates} saving={saving} onUpdate={updateStep} onAdd={addStep} onRemove={removeStep} onSave={handleSaveSequence} />
      )}

      {activeTab === 'prospects' && (
        <ProspectsTab
          prospects={prospects} total={prospectsTotal} page={prospectsPage} search={prospectsSearch}
          showAssign={showAssign} assignFilters={assignFilters}
          onSearch={(v) => { setProspectsSearch(v); setProspectsPage(1); }} onPage={setProspectsPage}
          onShowAssign={() => setShowAssign(true)} onAssignChange={setAssignFilters} onAssign={handleAssign} onCloseAssign={() => setShowAssign(false)}
        />
      )}

      {activeTab === 'analytics' && <AnalyticsTab metrics={metrics} />}

      {activeTab === 'settings' && <SettingsTab form={settingsForm} onChange={setSettingsForm} onSave={handleSaveSettings} onDelete={handleDelete} />}
    </div>
  );
}
