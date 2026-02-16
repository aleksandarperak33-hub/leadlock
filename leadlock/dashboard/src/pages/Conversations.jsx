import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import ConversationThread from '../components/ConversationThread';
import LeadStatusBadge from '../components/LeadStatusBadge';
import { MessageSquare, User, Calendar, ArrowLeft } from 'lucide-react';
import { format } from 'date-fns';

export default function Conversations() {
  const { leadId } = useParams();
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [selectedLead, setSelectedLead] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [leadDetail, setLeadDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLeads = async () => {
      try {
        const data = await api.getLeads({ per_page: 50 });
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
    const interval = setInterval(fetchConversation, 10000);
    return () => clearInterval(interval);
  }, [selectedLead]);

  const selectLead = (id) => {
    setSelectedLead(id);
    navigate(`/conversations/${id}`, { replace: true });
  };

  return (
    <div className="animate-page-in">
      {/* Header */}
      <h1 className="text-xl font-bold tracking-tight text-gray-900 mb-6">
        Conversations
      </h1>

      <div className="flex gap-4 h-[calc(100vh-180px)]">
        {/* Lead sidebar */}
        <div className="w-72 flex-shrink-0 bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden hidden lg:flex lg:flex-col">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
              Recent Leads
            </p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {leads.map(lead => {
              const isSelected = selectedLead === lead.id;
              return (
                <button
                  key={lead.id}
                  onClick={() => selectLead(lead.id)}
                  className={`w-full text-left px-4 py-3 border-b border-gray-100 transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-indigo-50'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium truncate ${
                      isSelected ? 'text-indigo-700' : 'text-gray-900'
                    }`}>
                      {lead.first_name || 'Unknown'} {lead.last_name || ''}
                    </span>
                    <LeadStatusBadge status={lead.state} />
                  </div>
                  <p className="text-[11px] mt-0.5 text-gray-400">
                    {lead.source?.replace('_', ' ')} &middot; {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '\u2014'}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Conversation panel */}
        <div className="flex-1 bg-white border border-gray-200 rounded-xl shadow-sm flex flex-col overflow-hidden">
          {!selectedLead ? (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
              <MessageSquare className="w-8 h-8 mb-3" strokeWidth={1.5} />
              <p className="text-sm">Select a lead to view their conversation</p>
            </div>
          ) : (
            <>
              {/* Conversation header */}
              {leadDetail?.lead && (
                <div className="px-5 py-4 border-b border-gray-100">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => { setSelectedLead(null); navigate('/conversations'); }}
                      className="lg:hidden text-gray-400 hover:text-gray-600 cursor-pointer"
                    >
                      <ArrowLeft className="w-4 h-4" />
                    </button>
                    <div className="w-9 h-9 rounded-lg bg-indigo-50 flex items-center justify-center">
                      <User className="w-4 h-4 text-indigo-500" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {leadDetail.lead.first_name || 'Unknown'} {leadDetail.lead.last_name || ''}
                      </p>
                      <p className="text-[11px] font-mono text-gray-400">
                        {leadDetail.lead.phone_masked}
                      </p>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                      <LeadStatusBadge status={leadDetail.lead.state} />
                      <span className="text-[11px] capitalize text-gray-400">
                        {leadDetail.lead.source?.replace('_', ' ')}
                      </span>
                    </div>
                  </div>

                  {/* Booking info */}
                  {leadDetail.booking && (
                    <div className="mt-3 px-4 py-3 rounded-lg bg-emerald-50 border border-emerald-100">
                      <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 mb-0.5">
                        <Calendar className="w-3.5 h-3.5" />
                        Appointment Booked
                      </div>
                      <p className="text-[11px] text-gray-500">
                        {leadDetail.booking.appointment_date}
                        {leadDetail.booking.time_window_start && ` at ${leadDetail.booking.time_window_start}`}
                        {leadDetail.booking.tech_name && ` with ${leadDetail.booking.tech_name}`}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-5">
                <ConversationThread messages={conversations} />
              </div>

              {/* Timeline */}
              {leadDetail?.events?.length > 0 && (
                <div className="px-5 py-3 max-h-28 overflow-y-auto border-t border-gray-100 bg-gray-50">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-2">
                    Timeline
                  </p>
                  <div className="space-y-1">
                    {leadDetail.events.slice(-5).map(event => (
                      <div key={event.id} className="flex items-center gap-2 text-[11px]">
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
                        <span className="text-gray-500">
                          {event.action.replace('_', ' ')}
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
