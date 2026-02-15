import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import ConversationThread from '../components/ConversationThread';
import LeadStatusBadge from '../components/LeadStatusBadge';
import { MessageSquare, User, Calendar, Clock, ArrowLeft } from 'lucide-react';
import { format } from 'date-fns';

export default function Conversations() {
  const { leadId } = useParams();
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [selectedLead, setSelectedLead] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [leadDetail, setLeadDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load lead list
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

  // Auto-select lead from URL param
  useEffect(() => {
    if (leadId) {
      setSelectedLead(leadId);
    }
  }, [leadId]);

  // Load conversation when lead is selected
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
    <div>
      <h1 className="text-xl font-bold text-white mb-6">Conversations</h1>

      <div className="flex gap-4 h-[calc(100vh-180px)]">
        {/* Lead list panel */}
        <div className="w-80 flex-shrink-0 bg-slate-900 border border-slate-800 rounded-xl overflow-y-auto hidden lg:block">
          <div className="p-3 border-b border-slate-800">
            <p className="text-xs text-slate-400 font-medium">Recent Leads</p>
          </div>
          <div className="divide-y divide-slate-800/50">
            {leads.map(lead => (
              <button
                key={lead.id}
                onClick={() => selectLead(lead.id)}
                className={`w-full text-left px-4 py-3 transition-colors ${
                  selectedLead === lead.id ? 'bg-slate-800' : 'hover:bg-slate-800/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white font-medium truncate">
                    {lead.first_name || 'Unknown'} {lead.last_name || ''}
                  </span>
                  <LeadStatusBadge status={lead.state} />
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {lead.source?.replace('_', ' ')} &middot; {new Date(lead.created_at).toLocaleDateString()}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* Conversation panel */}
        <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl flex flex-col overflow-hidden">
          {!selectedLead ? (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500">
              <MessageSquare className="w-12 h-12 mb-3" />
              <p>Select a lead to view their conversation</p>
            </div>
          ) : (
            <>
              {/* Lead detail header */}
              {leadDetail?.lead && (
                <div className="px-5 py-4 border-b border-slate-800">
                  <div className="flex items-center gap-3 mb-2">
                    <button
                      onClick={() => { setSelectedLead(null); navigate('/conversations'); }}
                      className="lg:hidden text-slate-400"
                    >
                      <ArrowLeft className="w-5 h-5" />
                    </button>
                    <div className="w-10 h-10 bg-slate-800 rounded-full flex items-center justify-center">
                      <User className="w-5 h-5 text-slate-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white">
                        {leadDetail.lead.first_name || 'Unknown'} {leadDetail.lead.last_name || ''}
                      </p>
                      <p className="text-xs text-slate-500">{leadDetail.lead.phone_masked}</p>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                      <LeadStatusBadge status={leadDetail.lead.state} />
                      <span className="text-xs text-slate-500 capitalize">{leadDetail.lead.source?.replace('_', ' ')}</span>
                    </div>
                  </div>

                  {/* Booking card */}
                  {leadDetail.booking && (
                    <div className="mt-3 px-4 py-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                      <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium mb-1">
                        <Calendar className="w-4 h-4" />
                        Appointment Booked
                      </div>
                      <p className="text-xs text-slate-300">
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
                <div className="px-5 py-3 border-t border-slate-800 max-h-32 overflow-y-auto">
                  <p className="text-[10px] text-slate-500 font-medium mb-2 uppercase tracking-wider">Timeline</p>
                  <div className="space-y-1">
                    {leadDetail.events.slice(-5).map(event => (
                      <div key={event.id} className="flex items-center gap-2 text-[11px]">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
                        <span className="text-slate-500">{event.action.replace('_', ' ')}</span>
                        {event.duration_ms && (
                          <span className="text-slate-600">{event.duration_ms}ms</span>
                        )}
                        <span className="text-slate-600 ml-auto">
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
