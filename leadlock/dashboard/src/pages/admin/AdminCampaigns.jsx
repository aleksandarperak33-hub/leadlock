import { useState, useEffect } from 'react';
import { Send, Plus, Pause, Play, Edit2, Trash2, ChevronRight } from 'lucide-react';
import { api } from '../../api/client';

const STATUS_COLORS = {
  draft: { bg: 'rgba(148, 163, 184, 0.1)', text: '#94a3b8' },
  active: { bg: 'rgba(52, 211, 153, 0.1)', text: '#34d399' },
  paused: { bg: 'rgba(251, 191, 36, 0.1)', text: '#fbbf24' },
  completed: { bg: 'rgba(96, 165, 250, 0.1)', text: '#60a5fa' },
};

const inputStyle = { background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-primary)' };

export default function AdminCampaigns() {
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
        <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }} />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Send className="w-5 h-5" style={{ color: '#a855f7' }} />
          <div>
            <h1 className="text-[20px] font-bold" style={{ color: 'var(--text-primary)' }}>Campaigns</h1>
            <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>{campaigns.length} campaigns</p>
          </div>
        </div>
        <button onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-medium text-white"
          style={{ background: '#a855f7' }}>
          <Plus className="w-3.5 h-3.5" /> New Campaign
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="rounded-xl p-5 mb-6" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <h2 className="text-[14px] font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>Create Campaign</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Name</label>
              <input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} placeholder="Q1 HVAC Outreach" />
            </div>
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Daily Limit</label>
              <input type="number" value={form.daily_limit} onChange={e => setForm({ ...form, daily_limit: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} />
            </div>
          </div>
          <div className="mb-4">
            <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Description</label>
            <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 rounded-md text-[13px] outline-none h-20 resize-none" style={inputStyle} placeholder="Campaign description..." />
          </div>

          {/* Sequence steps */}
          <div className="mb-4">
            <label className="block text-[11px] font-medium uppercase tracking-wider mb-2" style={{ color: 'var(--text-tertiary)' }}>Sequence Steps</label>
            <div className="space-y-2">
              {form.sequence_steps.map((step, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg p-3" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                  <span className="text-[12px] font-mono font-medium" style={{ color: 'var(--text-tertiary)' }}>Step {step.step}</span>
                  <ChevronRight className="w-3 h-3" style={{ color: 'var(--text-tertiary)' }} />
                  <span className="text-[12px] capitalize" style={{ color: 'var(--text-secondary)' }}>{step.channel}</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>after {step.delay_hours}h</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={!form.name}
              className="px-4 py-2 rounded-lg text-[13px] font-medium text-white disabled:opacity-50"
              style={{ background: '#a855f7' }}>
              Create Campaign
            </button>
            <button onClick={() => setShowCreate(false)}
              className="px-4 py-2 rounded-lg text-[13px] font-medium"
              style={{ color: 'var(--text-tertiary)', background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Campaigns list */}
      <div className="space-y-3">
        {campaigns.length === 0 ? (
          <div className="text-center py-16 rounded-xl" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <Send className="w-10 h-10 mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }} />
            <p className="text-[14px] font-medium" style={{ color: 'var(--text-secondary)' }}>No campaigns yet</p>
            <p className="text-[12px] mt-1" style={{ color: 'var(--text-tertiary)' }}>Create your first campaign to start automated outreach.</p>
          </div>
        ) : campaigns.map(c => (
          <div key={c.id} className="rounded-xl p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-[14px] font-semibold" style={{ color: 'var(--text-primary)' }}>{c.name}</h3>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium capitalize"
                    style={{ background: STATUS_COLORS[c.status]?.bg, color: STATUS_COLORS[c.status]?.text }}>
                    {c.status}
                  </span>
                </div>
                {c.description && (
                  <p className="text-[12px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{c.description}</p>
                )}
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Sent: {c.total_sent || 0}</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Opened: {c.total_opened || 0}</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Replied: {c.total_replied || 0}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => handleToggle(c)}
                  className="p-2 rounded-lg transition-colors hover:opacity-80"
                  style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                  {c.status === 'active'
                    ? <Pause className="w-3.5 h-3.5" style={{ color: '#fbbf24' }} />
                    : <Play className="w-3.5 h-3.5" style={{ color: '#34d399' }} />
                  }
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
