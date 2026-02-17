import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Plus, Pause, Play, ChevronRight } from 'lucide-react';
import { api } from '../../api/client';

const STATUS_BADGE = {
  draft: 'bg-gray-50 text-gray-700 border border-gray-200',
  active: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  paused: 'bg-amber-50 text-amber-700 border border-amber-100',
  completed: 'bg-blue-50 text-blue-700 border border-blue-100',
};

export default function AdminCampaigns() {
  const navigate = useNavigate();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    name: '', description: '', target_trades: [], target_locations: [],
    daily_limit: 25, sequence_steps: [
      { step: 1, channel: 'email', delay_hours: 0 },
      { step: 2, channel: 'email', delay_hours: 48 },
      { step: 3, channel: 'email', delay_hours: 96 },
    ],
  });

  useEffect(() => {
    loadCampaigns();
  }, []);

  const loadCampaigns = async () => {
    try {
      const data = await api.getCampaigns();
      setCampaigns(data.campaigns || []);
    } catch {
      // API not yet implemented, use empty list
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      await api.createCampaign(form);
      setShowCreate(false);
      setForm({ name: '', description: '', target_trades: [], target_locations: [], daily_limit: 25, sequence_steps: form.sequence_steps });
      loadCampaigns();
    } catch (err) {
      console.error('Failed to create campaign:', err);
    }
  };

  const handleToggle = async (campaign) => {
    try {
      if (campaign.status === 'active') {
        await api.pauseCampaign(campaign.id);
      } else {
        await api.resumeCampaign(campaign.id);
      }
      loadCampaigns();
    } catch (err) {
      console.error('Failed to toggle campaign:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-orange-50">
            <Send className="w-4.5 h-4.5 text-orange-600" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Campaigns</h1>
            <p className="text-sm text-gray-500">{campaigns.length} campaigns</p>
          </div>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 transition-colors cursor-pointer"
        >
          <Plus className="w-4 h-4" /> New Campaign
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 mb-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Create Campaign</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow"
                placeholder="Q1 HVAC Outreach"
              />
            </div>
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">Daily Limit</label>
              <input
                type="number"
                value={form.daily_limit}
                onChange={e => setForm({ ...form, daily_limit: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow"
              />
            </div>
          </div>
          <div className="mb-4">
            <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">Description</label>
            <textarea
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow h-20 resize-none"
              placeholder="Campaign description..."
            />
          </div>

          {/* Sequence steps */}
          <div className="mb-4">
            <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-2">Sequence Steps</label>
            <div className="space-y-2">
              {form.sequence_steps.map((step, i) => (
                <div key={i} className="flex items-center gap-3 bg-gray-50 border border-gray-100 rounded-lg p-3">
                  <span className="text-xs font-mono font-medium text-gray-500">Step {step.step}</span>
                  <ChevronRight className="w-3 h-3 text-gray-400" />
                  <span className="text-xs capitalize text-gray-700">{step.channel}</span>
                  <span className="text-xs text-gray-400">after {step.delay_hours}h</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              disabled={!form.name}
              className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 disabled:opacity-50 transition-colors cursor-pointer"
            >
              Create Campaign
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="px-4 py-2 rounded-lg text-sm font-medium text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Campaigns list */}
      <div className="space-y-3">
        {campaigns.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm text-center py-16">
            <Send className="w-10 h-10 mx-auto mb-3 text-gray-300" />
            <p className="text-sm font-medium text-gray-700">No campaigns yet</p>
            <p className="text-xs text-gray-400 mt-1">Create your first campaign to start automated outreach.</p>
          </div>
        ) : campaigns.map(c => (
          <div
            key={c.id}
            onClick={() => navigate(`/campaigns/${c.id}`)}
            className="bg-white border border-gray-200 rounded-xl shadow-sm p-4 hover:shadow-md transition-shadow cursor-pointer"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-gray-900">{c.name}</h3>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium capitalize ${STATUS_BADGE[c.status] || STATUS_BADGE.draft}`}>
                    {c.status}
                  </span>
                </div>
                {c.description && (
                  <p className="text-xs text-gray-400 mt-1">{c.description}</p>
                )}
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-xs text-gray-400">Sent: <span className="font-medium text-gray-600">{c.total_sent || 0}</span></span>
                  <span className="text-xs text-gray-400">Opened: <span className="font-medium text-gray-600">{c.total_opened || 0}</span></span>
                  <span className="text-xs text-gray-400">Replied: <span className="font-medium text-gray-600">{c.total_replied || 0}</span></span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={e => { e.stopPropagation(); handleToggle(c); }}
                  className="p-2 rounded-lg bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
                >
                  {c.status === 'active'
                    ? <Pause className="w-4 h-4 text-amber-500" />
                    : <Play className="w-4 h-4 text-emerald-500" />
                  }
                </button>
                <ChevronRight className="w-4 h-4 text-gray-300" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
