import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Plus, Pause, Play, ChevronRight, X } from 'lucide-react';
import { api } from '../../api/client';
import PageHeader from '../../components/ui/PageHeader';
import Badge from '../../components/ui/Badge';
import EmptyState from '../../components/ui/EmptyState';

const STATUS_VARIANT = {
  draft: 'neutral',
  active: 'success',
  paused: 'warning',
  completed: 'neutral',
};

const DEFAULT_STEPS = [
  { step: 1, channel: 'email', delay_hours: 0 },
  { step: 2, channel: 'email', delay_hours: 48 },
  { step: 3, channel: 'email', delay_hours: 96 },
];

const INITIAL_FORM = {
  name: '',
  description: '',
  target_trades: [],
  target_locations: [],
  daily_limit: 25,
  sequence_steps: DEFAULT_STEPS,
};

function CampaignCard({ campaign, onToggle, onClick }) {
  const totalSent = campaign.total_sent || 0;
  const totalOpened = campaign.total_opened || 0;
  const totalReplied = campaign.total_replied || 0;
  const openRate = totalSent > 0 ? ((totalOpened / totalSent) * 100).toFixed(1) : '0.0';
  const replyRate = totalSent > 0 ? ((totalReplied / totalSent) * 100).toFixed(1) : '0.0';

  return (
    <div
      onClick={onClick}
      className="bg-white border border-gray-200/60 rounded-2xl p-6 hover:shadow-md transition-shadow cursor-pointer"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 mb-1">
            <h3 className="text-lg font-semibold text-gray-900 truncate">
              {campaign.name}
            </h3>
            <Badge variant={STATUS_VARIANT[campaign.status] || 'neutral'}>
              {campaign.status}
            </Badge>
          </div>
          {campaign.description && (
            <p className="text-sm text-gray-500 line-clamp-2">
              {campaign.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 ml-4 shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); onToggle(campaign); }}
            className="p-2 rounded-xl bg-white border border-gray-200/60 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            {campaign.status === 'active'
              ? <Pause className="w-4 h-4 text-amber-500" />
              : <Play className="w-4 h-4 text-emerald-500" />
            }
          </button>
          <ChevronRight className="w-4 h-4 text-gray-300" />
        </div>
      </div>

      <div className="flex items-center gap-6 pt-3 border-t border-gray-100">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            Prospects
          </p>
          <p className="text-lg font-bold text-gray-900 font-mono mt-0.5">
            {campaign.prospect_count || 0}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            Sent
          </p>
          <p className="text-lg font-bold text-gray-900 font-mono mt-0.5">
            {totalSent}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            Open Rate
          </p>
          <p className="text-lg font-bold text-gray-900 font-mono mt-0.5">
            {openRate}%
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            Reply Rate
          </p>
          <p className="text-lg font-bold text-gray-900 font-mono mt-0.5">
            {replyRate}%
          </p>
        </div>
      </div>
    </div>
  );
}

function CreateModal({ form, onChange, onSubmit, onClose }) {
  const updateField = (field, value) => onChange({ ...form, [field]: value });

  const addStep = () => {
    const nextStep = {
      step: form.sequence_steps.length + 1,
      channel: 'email',
      delay_hours: form.sequence_steps.length === 0 ? 0 : 48,
    };
    updateField('sequence_steps', [...form.sequence_steps, nextStep]);
  };

  const removeStep = (index) => {
    const updated = form.sequence_steps
      .filter((_, i) => i !== index)
      .map((s, i) => ({ ...s, step: i + 1 }));
    updateField('sequence_steps', updated);
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-gray-200/60">
          <h2 className="text-lg font-semibold text-gray-900">Create Campaign</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
              Campaign Name
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow"
              placeholder="Q1 HVAC Outreach"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
              Description
            </label>
            <textarea
              value={form.description}
              onChange={(e) => updateField('description', e.target.value)}
              className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow h-20 resize-none"
              placeholder="Campaign description..."
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
              Daily Limit
            </label>
            <input
              type="number"
              value={form.daily_limit}
              onChange={(e) => updateField('daily_limit', parseInt(e.target.value) || 0)}
              className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
              Sequence Steps
            </label>
            <div className="space-y-2">
              {form.sequence_steps.map((step, i) => (
                <div key={i} className="flex items-center gap-3 bg-gray-50/80 border border-gray-100 rounded-xl p-3">
                  <span className="text-xs font-bold text-orange-500 font-mono">
                    {step.step}
                  </span>
                  <ChevronRight className="w-3 h-3 text-gray-300" />
                  <span className="text-xs capitalize text-gray-700">
                    {step.channel}
                  </span>
                  <span className="text-xs text-gray-400">
                    after {step.delay_hours}h
                  </span>
                  <div className="flex-1" />
                  <button
                    onClick={() => removeStep(i)}
                    className="p-1 rounded-lg hover:bg-red-50 transition-colors cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5 text-gray-400 hover:text-red-500" />
                  </button>
                </div>
              ))}
            </div>
            <button
              onClick={addStep}
              className="flex items-center gap-1.5 mt-2 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 border border-gray-200 border-dashed hover:border-orange-300 hover:text-orange-600 transition-colors cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" /> Add Step
            </button>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-200/60">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm font-medium text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={onSubmit}
            disabled={!form.name}
            className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 disabled:opacity-50 transition-colors cursor-pointer"
          >
            Create
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminCampaigns() {
  const navigate = useNavigate();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);

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
      setForm({ ...INITIAL_FORM, sequence_steps: DEFAULT_STEPS });
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
        <div className="w-6 h-6 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <PageHeader
        title="Campaigns"
        subtitle={`${campaigns.length} campaign${campaigns.length !== 1 ? 's' : ''}`}
        actions={
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer"
          >
            <Plus className="w-4 h-4" /> New Campaign
          </button>
        }
      />

      {showCreate && (
        <CreateModal
          form={form}
          onChange={setForm}
          onSubmit={handleCreate}
          onClose={() => setShowCreate(false)}
        />
      )}

      {campaigns.length === 0 ? (
        <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm">
          <EmptyState
            icon={Send}
            title="No campaigns yet"
            description="Create your first campaign to start automated outreach."
            action={
              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer"
              >
                <Plus className="w-4 h-4" /> Create Campaign
              </button>
            }
          />
        </div>
      ) : (
        <div className="space-y-4">
          {campaigns.map((c) => (
            <CampaignCard
              key={c.id}
              campaign={c}
              onToggle={handleToggle}
              onClick={() => navigate(`/campaigns/${c.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
