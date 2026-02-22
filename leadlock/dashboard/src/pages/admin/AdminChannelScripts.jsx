import { useState, useEffect } from 'react';
import { MessageSquare, Copy, Send, SkipForward, AlertCircle } from 'lucide-react';
import { api } from '../../api/client';
import PageHeader from '../../components/ui/PageHeader';
import Badge from '../../components/ui/Badge';
import EmptyState from '../../components/ui/EmptyState';

const STATUS_TABS = ['All', 'Generated', 'Sent', 'Skipped'];
const CHANNEL_OPTIONS = ['All', 'linkedin_dm', 'cold_call', 'facebook_group'];

const STATUS_VARIANT = {
  generated: 'warning',
  sent: 'success',
  skipped: 'neutral',
};

const CHANNEL_VARIANT = {
  linkedin_dm: 'info',
  cold_call: 'neutral',
  facebook_group: 'warning',
};

function ScriptCard({ script, onSent, onSkipped }) {
  const [actionLoading, setActionLoading] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(script.script_text || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleMarkSent = async () => {
    setActionLoading('sent');
    try {
      await api.markScriptSent(script.id);
      onSent(script.id);
    } catch {
      setActionLoading(null);
    }
  };

  const handleSkip = async () => {
    setActionLoading('skipped');
    try {
      await api.skipScript(script.id);
      onSkipped(script.id);
    } catch {
      setActionLoading(null);
    }
  };

  const preview = (script.script_text || '').slice(0, 240);

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="text-xs text-gray-500 mb-0.5">
            {script.prospect_name || script.prospect_id || 'Unknown prospect'}
            {script.prospect_company ? ` · ${script.prospect_company}` : ''}
          </div>
          {script.prospect_title && (
            <div className="text-xs text-gray-400">{script.prospect_title}</div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge variant={CHANNEL_VARIANT[script.channel] || 'neutral'}>{script.channel}</Badge>
          <Badge variant={STATUS_VARIANT[script.status] || 'neutral'}>{script.status}</Badge>
        </div>
      </div>

      <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line mb-4 bg-gray-50 rounded-xl p-3 border border-gray-100">
        {preview}{(script.script_text || '').length > 240 ? '…' : ''}
      </p>

      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 cursor-pointer"
        >
          <Copy className="w-3.5 h-3.5" />
          {copied ? 'Copied!' : 'Copy Script'}
        </button>

        {script.status === 'generated' && (
          <>
            <button
              onClick={handleMarkSent}
              disabled={!!actionLoading}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 cursor-pointer"
            >
              <Send className="w-3.5 h-3.5" />
              {actionLoading === 'sent' ? 'Marking…' : 'Mark Sent'}
            </button>
            <button
              onClick={handleSkip}
              disabled={!!actionLoading}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-gray-100 text-gray-500 hover:bg-gray-200 disabled:opacity-50 cursor-pointer"
            >
              <SkipForward className="w-3.5 h-3.5" />
              {actionLoading === 'skipped' ? 'Skipping…' : 'Skip'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function AdminChannelScripts() {
  const [scripts, setScripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('All');
  const [channelFilter, setChannelFilter] = useState('All');

  useEffect(() => {
    loadScripts();
  }, []);

  const loadScripts = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getChannelScripts();
      setScripts(Array.isArray(data) ? data : (data.items || []));
    } catch (err) {
      setError(err.message || 'Failed to load channel scripts.');
    } finally {
      setLoading(false);
    }
  };

  const handleSent = (id) => {
    setScripts((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: 'sent' } : s))
    );
  };

  const handleSkipped = (id) => {
    setScripts((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: 'skipped' } : s))
    );
  };

  const filtered = scripts.filter((s) => {
    const matchStatus = statusFilter === 'All' || s.status === statusFilter.toLowerCase();
    const matchChannel = channelFilter === 'All' || s.channel === channelFilter;
    return matchStatus && matchChannel;
  });

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
        title="Channel Scripts"
        subtitle={`${scripts.length} script${scripts.length !== 1 ? 's' : ''} generated`}
      />

      {error && (
        <div className="mb-4 flex items-center gap-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
          <p className="text-sm text-red-700 flex-1">{error}</p>
          <button onClick={loadScripts} className="text-xs font-medium text-red-600 hover:text-red-800 cursor-pointer">
            Retry
          </button>
        </div>
      )}

      <div className="bg-white border border-gray-200/60 rounded-2xl p-4 shadow-sm mb-4">
        <div className="flex flex-wrap gap-2 mb-3">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setStatusFilter(tab)}
              className={`text-xs font-medium px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
                statusFilter === tab
                  ? 'bg-orange-500 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {CHANNEL_OPTIONS.map((ch) => (
            <button
              key={ch}
              onClick={() => setChannelFilter(ch)}
              className={`text-xs font-medium px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
                channelFilter === ch
                  ? 'bg-gray-800 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {ch}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm">
          <EmptyState
            icon={MessageSquare}
            title="No scripts found"
            description="Channel scripts will appear here once prospects are processed."
          />
        </div>
      ) : (
        <div className="grid gap-4">
          {filtered.map((script) => (
            <ScriptCard
              key={script.id}
              script={script}
              onSent={handleSent}
              onSkipped={handleSkipped}
            />
          ))}
        </div>
      )}
    </div>
  );
}
