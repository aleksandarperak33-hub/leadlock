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
    <div>
      <h1 className="text-lg font-semibold tracking-tight mb-5" style={{ color: 'var(--text-primary)' }}>Conversations</h1>

      <div className="flex gap-3 h-[calc(100vh-180px)]">
        {/* Lead list */}
        <div
          className="w-72 flex-shrink-0 rounded-card overflow-y-auto hidden lg:block"
          style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
        >
          <div className="px-4 py-2.5" style={{ borderBottom: '1px solid var(--border)' }}>
            <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
              Recent Leads
            </p>
          </div>
          <div>
            {leads.map(lead => (
              <button
                key={lead.id}
                onClick={() => selectLead(lead.id)}
                className="w-full text-left px-4 py-2.5 transition-colors"
                style={{
                  background: selectedLead === lead.id ? 'var(--surface-2)' : 'transparent',
                  borderBottom: '1px solid var(--border)',
                }}
                onMouseEnter={e => { if (selectedLead !== lead.id) e.currentTarget.style.background = 'var(--surface-2)'; }}
                onMouseLeave={e => { if (selectedLead !== lead.id) e.currentTarget.style.background = 'transparent'; }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                    {lead.first_name || 'Unknown'} {lead.last_name || ''}
                  </span>
                  <LeadStatusBadge status={lead.state} />
                </div>
                <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                  {lead.source?.replace('_', ' ')} &middot; {new Date(lead.created_at).toLocaleDateString()}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* Conversation panel */}
        <div
          className="flex-1 rounded-card flex flex-col overflow-hidden"
          style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
        >
          {!selectedLead ? (
            <div className="flex-1 flex flex-col items-center justify-center" style={{ color: 'var(--text-tertiary)' }}>
              <MessageSquare className="w-8 h-8 mb-3" strokeWidth={1.5} />
              <p className="text-[13px]">Select a lead to view their conversation</p>
            </div>
          ) : (
            <>
              {leadDetail?.lead && (
                <div className="px-5 py-3.5" style={{ borderBottom: '1px solid var(--border)' }}>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => { setSelectedLead(null); navigate('/conversations'); }}
                      className="lg:hidden"
                      style={{ color: 'var(--text-tertiary)' }}
                    >
                      <ArrowLeft className="w-4 h-4" />
                    </button>
                    <div
                      className="w-8 h-8 rounded-md flex items-center justify-center"
                      style={{ background: 'var(--surface-3)' }}
                    >
                      <User className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
                    </div>
                    <div>
                      <p className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                        {leadDetail.lead.first_name || 'Unknown'} {leadDetail.lead.last_name || ''}
                      </p>
                      <p className="text-[11px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{leadDetail.lead.phone_masked}</p>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                      <LeadStatusBadge status={leadDetail.lead.state} />
                      <span className="text-[11px] capitalize" style={{ color: 'var(--text-tertiary)' }}>
                        {leadDetail.lead.source?.replace('_', ' ')}
                      </span>
                    </div>
                  </div>

                  {leadDetail.booking && (
                    <div
                      className="mt-3 px-3.5 py-2.5 rounded-md"
                      style={{ background: 'rgba(52, 211, 153, 0.06)', border: '1px solid rgba(52, 211, 153, 0.12)' }}
                    >
                      <div className="flex items-center gap-1.5 text-[12px] font-medium mb-0.5" style={{ color: '#34d399' }}>
                        <Calendar className="w-3.5 h-3.5" />
                        Appointment Booked
                      </div>
                      <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                        {leadDetail.booking.appointment_date}
                        {leadDetail.booking.time_window_start && ` at ${leadDetail.booking.time_window_start}`}
                        {leadDetail.booking.tech_name && ` with ${leadDetail.booking.tech_name}`}
                      </p>
                    </div>
                  )}
                </div>
              )}

              <div className="flex-1 overflow-y-auto px-5">
                <ConversationThread messages={conversations} />
              </div>

              {leadDetail?.events?.length > 0 && (
                <div className="px-5 py-2.5 max-h-28 overflow-y-auto" style={{ borderTop: '1px solid var(--border)' }}>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-tertiary)' }}>
                    Timeline
                  </p>
                  <div className="space-y-0.5">
                    {leadDetail.events.slice(-5).map(event => (
                      <div key={event.id} className="flex items-center gap-2 text-[11px]">
                        <span className="w-1 h-1 rounded-full" style={{ background: 'var(--text-tertiary)' }} />
                        <span style={{ color: 'var(--text-tertiary)' }}>{event.action.replace('_', ' ')}</span>
                        {event.duration_ms && (
                          <span className="font-mono" style={{ color: 'var(--text-tertiary)' }}>{event.duration_ms}ms</span>
                        )}
                        <span className="ml-auto font-mono" style={{ color: 'var(--text-tertiary)' }}>
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
