import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { POLL_INTERVALS, PER_PAGE } from '../lib/constants';
import { useDebounce } from '../hooks/useDebounce';
import PageHeader from '../components/ui/PageHeader';
import SearchInput from '../components/ui/SearchInput';
import StatusDot from '../components/ui/StatusDot';
import ConversationThread from '../components/ConversationThread';
import LeadStatusBadge from '../components/LeadStatusBadge';
import { MessageSquare, User, Calendar, ArrowLeft, Send, Loader2 } from 'lucide-react';
import { format } from 'date-fns';

/**
 * Maps a lead state to a StatusDot color.
 */
const stateToColor = (state) => {
  if (['booked', 'qualified', 'completed'].includes(state)) return 'green';
  if (['qualifying', 'booking', 'follow_up'].includes(state)) return 'yellow';
  if (['opted_out'].includes(state)) return 'red';
  return 'gray';
};

/**
 * Conversations -- Split-pane view with lead list (left) and message thread (right).
 * Fetches leads on mount and conversation data with 10-second auto-refresh.
 */
export default function Conversations() {
  const { leadId } = useParams();
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [selectedLead, setSelectedLead] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [leadDetail, setLeadDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedSearch = useDebounce(searchQuery, 300);

  useEffect(() => {
    const fetchLeads = async () => {
      try {
        const data = await api.getLeads({ per_page: PER_PAGE.CONVERSATIONS });
        setLeads(data.leads || []);
      } catch (e) {
        console.error('Failed to fetch leads:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchLeads();
  }, []);

  useEffect(() => {
    if (leadId) setSelectedLead(leadId);
  }, [leadId]);

  useEffect(() => {
    if (!selectedLead) return;
    const fetchConversation = async () => {
      try {
        const [detail, convos] = await Promise.all([
          api.getLead(selectedLead),
          api.getConversations(selectedLead),
        ]);
        setLeadDetail(detail);
        setConversations(convos || []);
      } catch (e) {
        console.error('Failed to fetch conversation:', e);
      }
    };
    fetchConversation();
    const interval = setInterval(fetchConversation, POLL_INTERVALS.CONVERSATIONS);
    return () => clearInterval(interval);
  }, [selectedLead]);

  const selectLead = (id) => {
    setSelectedLead(id);
    navigate(`/conversations/${id}`, { replace: true });
  };

  const filteredLeads = debouncedSearch
    ? leads.filter((lead) => {
        const name =
          `${lead.first_name || ''} ${lead.last_name || ''}`.toLowerCase();
        return name.includes(debouncedSearch.toLowerCase());
      })
    : leads;

  return (
    <div className="space-y-0">
      <PageHeader title="Conversations" />

      <div className="flex h-[calc(100vh-180px)]">
        {/* Left panel - Lead list */}
        <div className="w-80 flex-shrink-0 border-r border-gray-200/60 bg-white hidden lg:flex lg:flex-col">
          <div className="p-3 border-b border-gray-200/60">
            <SearchInput
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder="Search leads..."
            />
          </div>

          <div className="flex-1 overflow-y-auto">
            {filteredLeads.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-8">
                No leads found
              </p>
            )}
            {filteredLeads.map((lead) => {
              const isSelected = selectedLead === lead.id;
              return (
                <button
                  key={lead.id}
                  onClick={() => selectLead(lead.id)}
                  className={`w-full text-left px-4 py-3 border-b border-gray-100 transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-orange-50/50 border-l-2 border-l-orange-500'
                      : 'hover:bg-gray-50/50 border-l-2 border-l-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-sm font-medium text-gray-900 truncate">
                      {lead.first_name || 'Unknown'} {lead.last_name || ''}
                    </span>
                    <span className="text-xs text-gray-400 flex-shrink-0 ml-2">
                      {lead.created_at
                        ? format(new Date(lead.created_at), 'MMM d')
                        : '\u2014'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <StatusDot color={stateToColor(lead.state)} />
                    <span className="text-xs text-gray-400 capitalize">
                      {lead.state?.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 truncate mt-0.5">
                    {lead.source?.replaceAll('_', ' ')}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right panel - Conversation thread */}
        <div className="flex-1 bg-[#FAFAFA] flex flex-col overflow-hidden">
          {!selectedLead ? (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
              <MessageSquare className="w-10 h-10 mb-3" strokeWidth={1.5} />
              <p className="text-sm">
                Select a lead to view their conversation
              </p>
            </div>
          ) : (
            <>
              {/* Conversation header */}
              {leadDetail?.lead && (
                <div className="px-6 py-4 border-b border-gray-200/60 bg-white">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => {
                        setSelectedLead(null);
                        navigate('/conversations');
                      }}
                      className="lg:hidden text-gray-400 hover:text-gray-600 cursor-pointer"
                    >
                      <ArrowLeft className="w-4 h-4" />
                    </button>
                    <div className="w-9 h-9 rounded-xl bg-orange-50 flex items-center justify-center">
                      <User className="w-4 h-4 text-orange-500" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {leadDetail.lead.first_name || 'Unknown'}{' '}
                        {leadDetail.lead.last_name || ''}
                      </p>
                      <p className="text-xs font-mono text-gray-400">
                        {leadDetail.lead.phone_masked}
                      </p>
                    </div>
                    <div className="ml-auto flex items-center gap-3">
                      <LeadStatusBadge status={leadDetail.lead.state} />
                      <span className="text-xs capitalize text-gray-400">
                        {leadDetail.lead.source?.replaceAll('_', ' ')}
                      </span>
                    </div>
                  </div>

                  {/* Booking info */}
                  {leadDetail.booking && (
                    <div className="mt-3 px-4 py-3 rounded-xl bg-emerald-50 border border-emerald-100">
                      <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 mb-0.5">
                        <Calendar className="w-3.5 h-3.5" />
                        Appointment Booked
                      </div>
                      <p className="text-xs text-gray-500">
                        {leadDetail.booking.appointment_date}
                        {leadDetail.booking.time_window_start &&
                          ` at ${leadDetail.booking.time_window_start}`}
                        {leadDetail.booking.tech_name &&
                          ` with ${leadDetail.booking.tech_name}`}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-6">
                <ConversationThread messages={conversations} />
              </div>

              {/* Reply input */}
              <ReplyCompose
                leadId={selectedLead}
                onSent={() => {
                  // Re-fetch conversations after sending
                  api.getConversations(selectedLead).then(c => setConversations(c || []));
                }}
              />

              {/* Timeline */}
              {leadDetail?.events?.length > 0 && (
                <div className="px-6 py-3 max-h-28 overflow-y-auto border-t border-gray-200/60 bg-white">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                    Timeline
                  </p>
                  <div className="space-y-1">
                    {leadDetail.events.slice(-5).map((event) => (
                      <div
                        key={event.id}
                        className="flex items-center gap-2 text-xs"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
                        <span className="text-gray-500">
                          {event.action?.replaceAll('_', ' ')}
                        </span>
                        {event.duration_ms && (
                          <span className="font-mono text-gray-400">
                            {event.duration_ms}ms
                          </span>
                        )}
                        <span className="ml-auto font-mono text-gray-400">
                          {format(new Date(event.created_at), 'h:mm a')}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ReplyCompose({ leadId, onSent }) {
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  const handleSend = async () => {
    if (!message.trim() || sending) return;
    setSending(true);
    setError(null);
    try {
      await api.sendReply(leadId, message.trim());
      setMessage('');
      onSent();
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="px-6 py-3 border-t border-gray-200/60 bg-white">
      {error && (
        <p className="text-xs text-red-500 mb-2">{error}</p>
      )}
      <div className="flex items-end gap-2">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a reply..."
          rows={1}
          className="flex-1 px-4 py-2.5 text-sm bg-gray-50 border border-gray-200 rounded-xl outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100 placeholder:text-gray-400 text-gray-900 transition-all resize-none"
        />
        <button
          onClick={handleSend}
          disabled={!message.trim() || sending}
          className="flex items-center justify-center w-10 h-10 rounded-xl bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer disabled:cursor-not-allowed flex-shrink-0"
          aria-label="Send reply"
        >
          {sending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </div>
    </div>
  );
}
