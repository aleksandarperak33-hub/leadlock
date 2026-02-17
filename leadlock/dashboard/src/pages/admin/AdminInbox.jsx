import { useState, useEffect, useCallback } from 'react';
import {
  Inbox, Mail, MessageSquare, ChevronRight, Clock,
  Building2, MapPin, Phone, Send, Eye, AlertTriangle,
  CheckCircle2, XCircle, Ban, Filter,
} from 'lucide-react';
import { api } from '../../api/client';

const STATUS_BADGE = {
  cold: 'bg-gray-100 text-gray-600',
  contacted: 'bg-blue-50 text-blue-600',
  demo_scheduled: 'bg-orange-50 text-orange-600',
  won: 'bg-emerald-50 text-emerald-600',
  lost: 'bg-red-50 text-red-600',
};

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function AdminInbox() {
  const [conversations, setConversations] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [campaignFilter, setCampaignFilter] = useState('');
  const [campaigns, setCampaigns] = useState([]);

  // Thread state
  const [selectedId, setSelectedId] = useState(null);
  const [thread, setThread] = useState(null);
  const [threadLoading, setThreadLoading] = useState(false);

  const loadConversations = useCallback(async () => {
    try {
      setLoading(true);
      const params = { page, per_page: 25 };
      if (campaignFilter) params.campaign_id = campaignFilter;
      const data = await api.getInbox(params);
      setConversations(data.conversations || []);
      setTotal(data.total || 0);
    } catch {
      // API may not be ready
    } finally {
      setLoading(false);
    }
  }, [page, campaignFilter]);

  const loadCampaigns = useCallback(async () => {
    try {
      const data = await api.getCampaigns();
      setCampaigns(data.campaigns || []);
    } catch {
      // campaigns endpoint may not be ready
    }
  }, []);

  const loadThread = useCallback(async (prospectId) => {
    setThreadLoading(true);
    try {
      const data = await api.getInboxThread(prospectId);
      setThread(data);
    } catch {
      setThread(null);
    } finally {
      setThreadLoading(false);
    }
  }, []);

  useEffect(() => { loadConversations(); loadCampaigns(); }, [loadConversations, loadCampaigns]);

  const handleSelect = (prospectId) => {
    setSelectedId(prospectId);
    loadThread(prospectId);
  };

  const handleStatusChange = async (status) => {
    if (!selectedId) return;
    try {
      await api.updateProspect(selectedId, { status });
      loadConversations();
      loadThread(selectedId);
    } catch (err) {
      console.error('Status update failed:', err);
    }
  };

  const handleBlacklist = async () => {
    if (!selectedId || !confirm('Blacklist this prospect? They will not receive further emails.')) return;
    try {
      await api.blacklistProspect(selectedId);
      loadConversations();
      setSelectedId(null);
      setThread(null);
    } catch (err) {
      console.error('Blacklist failed:', err);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-orange-50">
            <Inbox className="w-4.5 h-4.5 text-orange-600" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Inbox</h1>
            <p className="text-sm text-gray-500">{total} conversations with replies</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-gray-400" />
          <select
            value={campaignFilter}
            onChange={e => { setCampaignFilter(e.target.value); setPage(1); }}
            className="px-2 py-1.5 bg-white border border-gray-200 rounded-lg text-xs text-gray-700 outline-none focus:border-orange-500 cursor-pointer"
          >
            <option value="">All Campaigns</option>
            {campaigns.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Split pane */}
      <div className="flex gap-0 bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden" style={{ height: 'calc(100vh - 200px)' }}>
        {/* Left pane: conversation list */}
        <div className="w-[360px] border-r border-gray-200 flex flex-col shrink-0">
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <div className="w-5 h-5 border-2 border-orange-600 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : conversations.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-6">
                <Inbox className="w-10 h-10 text-gray-300 mb-3" />
                <p className="text-sm font-medium text-gray-700">No replies yet</p>
                <p className="text-xs text-gray-400 mt-1">Check back when prospects respond to your outreach.</p>
              </div>
            ) : (
              conversations.map(conv => (
                <button
                  key={conv.prospect_id}
                  onClick={() => handleSelect(conv.prospect_id)}
                  className={`w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors cursor-pointer ${
                    selectedId === conv.prospect_id ? 'bg-orange-50/50 border-l-2 border-l-orange-500' : ''
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-gray-900 truncate">
                          {conv.prospect_name}
                        </span>
                        {conv.campaign_name && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-orange-50 text-orange-600 whitespace-nowrap">
                            {conv.campaign_name}
                          </span>
                        )}
                      </div>
                      {conv.prospect_company && (
                        <p className="text-[11px] text-gray-400 truncate">{conv.prospect_company}</p>
                      )}
                      <p className="text-[11px] text-gray-500 truncate mt-0.5">
                        {conv.last_reply_snippet || 'No preview available'}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1 ml-2 shrink-0">
                      <span className="text-[10px] text-gray-400 whitespace-nowrap">
                        {timeAgo(conv.last_reply_at)}
                      </span>
                      <span className="flex items-center gap-1 text-[10px] text-gray-400">
                        <MessageSquare className="w-2.5 h-2.5" /> {conv.reply_count}
                      </span>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>

          {/* Pagination */}
          {total > 25 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-gray-100">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="px-2 py-1 rounded text-[10px] text-gray-500 bg-gray-50 disabled:opacity-40 cursor-pointer"
              >
                Prev
              </button>
              <span className="text-[10px] text-gray-400">{page}/{Math.ceil(total / 25)}</span>
              <button
                onClick={() => setPage(page + 1)}
                disabled={page >= Math.ceil(total / 25)}
                className="px-2 py-1 rounded text-[10px] text-gray-500 bg-gray-50 disabled:opacity-40 cursor-pointer"
              >
                Next
              </button>
            </div>
          )}
        </div>

        {/* Right pane: email thread */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {!selectedId ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Mail className="w-10 h-10 text-gray-300 mb-3" />
              <p className="text-sm font-medium text-gray-600">Select a conversation</p>
              <p className="text-xs text-gray-400 mt-1">Click on a prospect to view their email thread.</p>
            </div>
          ) : threadLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-5 h-5 border-2 border-orange-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : thread ? (
            <>
              {/* Prospect header */}
              <div className="px-5 py-3 border-b border-gray-100 bg-gray-50/50 shrink-0">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-semibold text-gray-900">{thread.prospect.name}</h2>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium capitalize ${STATUS_BADGE[thread.prospect.status] || 'bg-gray-100 text-gray-600'}`}>
                        {thread.prospect.status}
                      </span>
                      {thread.prospect.campaign_name && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-orange-50 text-orange-600">
                          {thread.prospect.campaign_name}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      {thread.prospect.company && (
                        <span className="flex items-center gap-1 text-[11px] text-gray-400">
                          <Building2 className="w-3 h-3" /> {thread.prospect.company}
                        </span>
                      )}
                      {thread.prospect.trade_type && (
                        <span className="text-[11px] text-gray-400 capitalize">{thread.prospect.trade_type}</span>
                      )}
                      {(thread.prospect.city || thread.prospect.state_code) && (
                        <span className="flex items-center gap-1 text-[11px] text-gray-400">
                          <MapPin className="w-3 h-3" /> {[thread.prospect.city, thread.prospect.state_code].filter(Boolean).join(', ')}
                        </span>
                      )}
                      {thread.prospect.email && (
                        <span className="text-[11px] text-gray-400 font-mono">{thread.prospect.email}</span>
                      )}
                      {thread.prospect.phone && (
                        <span className="flex items-center gap-1 text-[11px] text-gray-400">
                          <Phone className="w-3 h-3" /> {thread.prospect.phone}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleStatusChange('won')}
                      className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition-colors cursor-pointer"
                      title="Mark Won"
                    >
                      <CheckCircle2 className="w-3 h-3" /> Won
                    </button>
                    <button
                      onClick={() => handleStatusChange('lost')}
                      className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium text-red-600 bg-red-50 hover:bg-red-100 transition-colors cursor-pointer"
                      title="Mark Lost"
                    >
                      <XCircle className="w-3 h-3" /> Lost
                    </button>
                    <button
                      onClick={handleBlacklist}
                      className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium text-gray-500 bg-gray-100 hover:bg-gray-200 transition-colors cursor-pointer"
                      title="Blacklist"
                    >
                      <Ban className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Email thread */}
              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
                {thread.emails.map(email => (
                  <div
                    key={email.id}
                    className={`rounded-xl p-4 ${
                      email.direction === 'outbound'
                        ? 'bg-gray-50 border border-gray-100'
                        : 'bg-orange-50/50 border border-orange-100'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {email.direction === 'outbound' ? (
                          <span className="flex items-center gap-1 text-[10px] font-medium text-gray-500">
                            <Send className="w-3 h-3" /> Outbound
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-[10px] font-medium text-orange-600">
                            <MessageSquare className="w-3 h-3" /> Reply
                          </span>
                        )}
                        {email.sequence_step > 0 && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-gray-100 text-gray-500">
                            Step {email.sequence_step}
                          </span>
                        )}
                        {/* Delivery status badges */}
                        {email.direction === 'outbound' && (
                          <div className="flex items-center gap-1">
                            {email.opened_at && (
                              <span className="flex items-center gap-0.5 text-[9px] text-emerald-600">
                                <Eye className="w-2.5 h-2.5" /> Opened
                              </span>
                            )}
                            {email.clicked_at && (
                              <span className="flex items-center gap-0.5 text-[9px] text-blue-600">
                                <ChevronRight className="w-2.5 h-2.5" /> Clicked
                              </span>
                            )}
                            {email.bounced_at && (
                              <span className="flex items-center gap-0.5 text-[9px] text-red-600">
                                <AlertTriangle className="w-2.5 h-2.5" /> Bounced
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                      <span className="flex items-center gap-1 text-[10px] text-gray-400">
                        <Clock className="w-3 h-3" />
                        {email.sent_at ? new Date(email.sent_at).toLocaleString() : '—'}
                      </span>
                    </div>
                    {email.subject && (
                      <p className="text-xs font-medium text-gray-700 mb-1">{email.subject}</p>
                    )}
                    <div className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">
                      {email.body_text || (email.body_html ? email.body_html.replace(/<[^>]+>/g, '') : '(no content)')}
                    </div>
                  </div>
                ))}
                {thread.emails.length === 0 && (
                  <p className="text-xs text-gray-400 text-center py-8">No emails in this thread.</p>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs text-gray-400">Failed to load thread.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
