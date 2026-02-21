import { useState, useEffect, useCallback } from 'react';
import {
  Inbox, Mail, MessageSquare, Clock,
  Building2, MapPin, Phone, Send, Eye, AlertTriangle,
  CheckCircle2, XCircle, Ban, ChevronRight, Filter,
} from 'lucide-react';
import { api } from '../../api/client';
import PageHeader from '../../components/ui/PageHeader';
import Badge from '../../components/ui/Badge';
import SearchInput from '../../components/ui/SearchInput';
import EmptyState from '../../components/ui/EmptyState';

const STATUS_VARIANT = {
  cold: 'neutral',
  contacted: 'info',
  demo_scheduled: 'warning',
  won: 'success',
  lost: 'danger',
};

const FILTER_TABS = [
  { id: 'all', label: 'All' },
  { id: 'replies', label: 'Replies' },
  { id: 'sent', label: 'Sent Only' },
];

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

function ConversationItem({ conv, isActive, onSelect }) {
  const hasReplies = conv.reply_count > 0;

  return (
    <button
      onClick={() => onSelect(conv.prospect_id)}
      className={`w-full text-left px-4 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer ${
        isActive ? 'bg-orange-50/50 border-l-2 border-l-orange-500' : ''
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {conv.unread && (
              <span className="w-2 h-2 rounded-full bg-orange-500 shrink-0" />
            )}
            <span className="text-sm font-medium text-gray-900 truncate">
              {conv.prospect_name}
            </span>
            {conv.campaign_name && (
              <Badge variant="warning" size="sm">
                {conv.campaign_name}
              </Badge>
            )}
            {!hasReplies && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-500">
                No replies yet
              </span>
            )}
          </div>
          {conv.prospect_company && (
            <p className="text-xs text-gray-500 truncate mt-0.5">
              {conv.prospect_company}
            </p>
          )}
          <p className="text-xs text-gray-400 truncate mt-0.5">
            {conv.last_reply_snippet || 'No preview available'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 ml-3 shrink-0">
          <span className="text-xs text-gray-400 font-mono whitespace-nowrap">
            {timeAgo(conv.last_activity_at || conv.last_inbound_at || conv.last_outbound_at)}
          </span>
          <div className="flex items-center gap-2">
            {conv.sent_count > 0 && (
              <span className="flex items-center gap-0.5 text-xs text-gray-400">
                <Send className="w-3 h-3" /> {conv.sent_count}
              </span>
            )}
            {hasReplies && (
              <span className="flex items-center gap-0.5 text-xs text-orange-500">
                <MessageSquare className="w-3 h-3" /> {conv.reply_count}
              </span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

function ThreadHeader({ prospect, onStatusChange, onBlacklist }) {
  return (
    <div className="px-5 py-4 border-b border-gray-200/60 bg-white shrink-0">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-lg font-semibold text-gray-900">
              {prospect.name}
            </h2>
            <Badge variant={STATUS_VARIANT[prospect.status] || 'neutral'}>
              {prospect.status}
            </Badge>
            {prospect.campaign_name && (
              <Badge variant="warning" size="sm">
                {prospect.campaign_name}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-4 mt-1.5">
            {prospect.company && (
              <span className="flex items-center gap-1 text-xs text-gray-500">
                <Building2 className="w-3 h-3" /> {prospect.company}
              </span>
            )}
            {prospect.trade_type && (
              <span className="text-xs text-gray-500 capitalize">
                {prospect.trade_type}
              </span>
            )}
            {(prospect.city || prospect.state_code) && (
              <span className="flex items-center gap-1 text-xs text-gray-500">
                <MapPin className="w-3 h-3" /> {[prospect.city, prospect.state_code].filter(Boolean).join(', ')}
              </span>
            )}
            {prospect.email && (
              <span className="text-xs text-gray-400 font-mono">
                {prospect.email}
              </span>
            )}
            {prospect.phone && (
              <span className="flex items-center gap-1 text-xs text-gray-500">
                <Phone className="w-3 h-3" /> {prospect.phone}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onStatusChange('won')}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200/60 hover:bg-emerald-100 transition-colors cursor-pointer"
          >
            <CheckCircle2 className="w-3 h-3" /> Won
          </button>
          <button
            onClick={() => onStatusChange('lost')}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 bg-red-50 border border-red-200/60 hover:bg-red-100 transition-colors cursor-pointer"
          >
            <XCircle className="w-3 h-3" /> Lost
          </button>
          <button
            onClick={onBlacklist}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            <Ban className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

function EmailMessage({ email }) {
  const isOutbound = email.direction === 'outbound';

  return (
    <div
      className={`rounded-xl border p-4 mb-3 ${
        isOutbound
          ? 'bg-orange-50/30 border-orange-200/40'
          : 'bg-white border-gray-200/60'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {isOutbound ? (
            <span className="flex items-center gap-1 text-xs font-medium text-gray-500">
              <Send className="w-3 h-3" /> Sent
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs font-medium text-orange-600">
              <MessageSquare className="w-3 h-3" /> Reply
            </span>
          )}
          {email.sequence_step > 0 && (
            <Badge variant="neutral" size="sm">
              Step {email.sequence_step}
            </Badge>
          )}
          {isOutbound && (
            <div className="flex items-center gap-1.5">
              {email.opened_at && (
                <span className="flex items-center gap-0.5 text-xs text-emerald-600">
                  <Eye className="w-3 h-3" /> Opened
                </span>
              )}
              {email.clicked_at && (
                <span className="flex items-center gap-0.5 text-xs text-blue-600">
                  <ChevronRight className="w-3 h-3" /> Clicked
                </span>
              )}
              {email.bounced_at && (
                <span className="flex items-center gap-0.5 text-xs text-red-600">
                  <AlertTriangle className="w-3 h-3" /> Bounced
                </span>
              )}
            </div>
          )}
        </div>
        <span className="flex items-center gap-1 text-xs text-gray-400 font-mono">
          <Clock className="w-3 h-3" />
          {email.sent_at ? new Date(email.sent_at).toLocaleString() : '--'}
        </span>
      </div>
      {email.subject && (
        <p className="text-sm font-medium text-gray-700 mb-1">
          {email.subject}
        </p>
      )}
      <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">
        {email.body_text || (email.body_html ? email.body_html.replace(/<[^>]+>/g, '') : '(no content)')}
      </div>
    </div>
  );
}

export default function AdminInbox() {
  const [conversations, setConversations] = useState([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState({ total_conversations: 0, with_replies: 0, without_replies: 0 });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [campaignFilter, setCampaignFilter] = useState('');
  const [inboxFilter, setInboxFilter] = useState('all');
  const [campaigns, setCampaigns] = useState([]);
  const [search, setSearch] = useState('');

  const [selectedId, setSelectedId] = useState(null);
  const [thread, setThread] = useState(null);
  const [threadLoading, setThreadLoading] = useState(false);

  const loadConversations = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params = { page, per_page: 25, filter: inboxFilter };
      if (campaignFilter) params.campaign_id = campaignFilter;
      const data = await api.getInbox(params);
      setConversations(data.conversations || []);
      setTotal(data.total || 0);
      setCounts({
        total_conversations: data.total_conversations ?? 0,
        with_replies: data.with_replies ?? 0,
        without_replies: data.without_replies ?? 0,
      });
    } catch (err) {
      setError('Failed to load inbox. Please try again.');
      setConversations([]);
    } finally {
      setLoading(false);
    }
  }, [page, campaignFilter, inboxFilter]);

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

  const handleFilterChange = (newFilter) => {
    setInboxFilter(newFilter);
    setPage(1);
    setSelectedId(null);
    setThread(null);
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

  const filteredConversations = search
    ? conversations.filter((c) =>
        (c.prospect_name || '').toLowerCase().includes(search.toLowerCase()) ||
        (c.prospect_company || '').toLowerCase().includes(search.toLowerCase())
      )
    : conversations;

  const subtitleText =
    inboxFilter === 'all'
      ? `${counts.total_conversations} conversations`
      : inboxFilter === 'replies'
        ? `${counts.with_replies} with replies`
        : `${counts.without_replies} awaiting reply`;

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <PageHeader
        title="Inbox"
        subtitle={subtitleText}
      />

      {/* Filter tabs */}
      <div className="flex items-center gap-1 mb-4">
        {FILTER_TABS.map((tab) => {
          const count =
            tab.id === 'all' ? counts.total_conversations
            : tab.id === 'replies' ? counts.with_replies
            : counts.without_replies;

          return (
            <button
              key={tab.id}
              onClick={() => handleFilterChange(tab.id)}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                inboxFilter === tab.id
                  ? 'bg-orange-50 text-orange-600 border border-orange-200/60'
                  : 'text-gray-500 hover:bg-gray-50 border border-transparent'
              }`}
            >
              {tab.label}
              <span className="ml-1.5 text-xs font-mono opacity-70">{count}</span>
            </button>
          );
        })}
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60">
          <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
          <p className="text-sm text-red-700 flex-1">{error}</p>
          <button
            onClick={loadConversations}
            className="text-xs font-medium text-red-600 hover:text-red-800 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      <div
        className="flex bg-white border border-gray-200/60 rounded-2xl shadow-sm overflow-hidden"
        style={{ height: 'calc(100vh - 260px)' }}
      >
        {/* Left pane */}
        <div className="w-[360px] border-r border-gray-200/60 flex flex-col shrink-0">
          <div className="p-3 border-b border-gray-100 space-y-2">
            <div className="flex items-center gap-2">
              <Filter className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              <select
                value={campaignFilter}
                onChange={(e) => { setCampaignFilter(e.target.value); setPage(1); }}
                className="w-full px-2.5 py-1.5 bg-white border border-gray-200 rounded-lg text-xs text-gray-700 outline-none focus:border-orange-500 cursor-pointer"
              >
                <option value="">All Campaigns</option>
                {campaigns.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Search conversations..."
            />
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : filteredConversations.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-6">
                <Inbox className="w-10 h-10 text-gray-300 mb-3" />
                <p className="text-sm font-medium text-gray-900">
                  {inboxFilter === 'replies' ? 'No replies yet' : inboxFilter === 'sent' ? 'No sent emails' : 'No conversations'}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  {inboxFilter === 'replies'
                    ? 'Check back when prospects respond to your outreach.'
                    : inboxFilter === 'sent'
                      ? 'Sent emails awaiting reply will appear here.'
                      : 'Start a campaign to see conversations here.'}
                </p>
              </div>
            ) : (
              filteredConversations.map((conv) => (
                <ConversationItem
                  key={conv.prospect_id}
                  conv={conv}
                  isActive={selectedId === conv.prospect_id}
                  onSelect={handleSelect}
                />
              ))
            )}
          </div>

          {total > 25 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-gray-100">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="px-2.5 py-1 rounded-lg text-xs text-gray-500 bg-gray-50 disabled:opacity-40 cursor-pointer"
              >
                Prev
              </button>
              <span className="text-xs text-gray-400 font-mono">
                {page}/{Math.ceil(total / 25)}
              </span>
              <button
                onClick={() => setPage(page + 1)}
                disabled={page >= Math.ceil(total / 25)}
                className="px-2.5 py-1 rounded-lg text-xs text-gray-500 bg-gray-50 disabled:opacity-40 cursor-pointer"
              >
                Next
              </button>
            </div>
          )}
        </div>

        {/* Right pane */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {!selectedId ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Mail className="w-12 h-12 text-gray-300 mb-4" />
              <p className="text-sm font-medium text-gray-900">
                Select a conversation
              </p>
              <p className="text-sm text-gray-400 mt-1">
                Click on a prospect to view their email thread.
              </p>
            </div>
          ) : threadLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : thread ? (
            <>
              <ThreadHeader
                prospect={thread.prospect}
                onStatusChange={handleStatusChange}
                onBlacklist={handleBlacklist}
              />
              <div className="flex-1 overflow-y-auto px-5 py-4">
                {(thread.emails || []).map((email) => (
                  <EmailMessage key={email.id} email={email} />
                ))}
                {(thread.emails || []).length === 0 && (
                  <p className="text-sm text-gray-400 text-center py-12">
                    No emails in this thread.
                  </p>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-gray-400">Failed to load thread.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
