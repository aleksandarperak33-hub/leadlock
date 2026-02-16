import { format } from 'date-fns';
import { Bot, MessageSquare } from 'lucide-react';

const AGENT_LABELS = {
  intake: 'Intake',
  qualify: 'Qualify',
  book: 'Book',
  followup: 'Follow-Up',
};

export default function ConversationThread({ messages = [] }) {
  if (!messages.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16" style={{ color: 'var(--text-tertiary)' }}>
        <MessageSquare className="w-8 h-8 mb-3" strokeWidth={1.5} />
        <p className="text-[13px]">No messages yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 py-4">
      {messages.map((msg) => {
        const isOutbound = msg.direction === 'outbound';
        return (
          <div key={msg.id} className={`flex ${isOutbound ? 'justify-end' : 'justify-start'}`}>
            <div className="max-w-[75%]">
              {isOutbound && msg.agent_id && (
                <div className="flex items-center gap-1 mb-1 justify-end">
                  <Bot className="w-3 h-3" style={{ color: 'var(--accent)' }} strokeWidth={1.75} />
                  <span className="text-[10px] font-medium" style={{ color: 'var(--text-tertiary)' }}>
                    {AGENT_LABELS[msg.agent_id] || msg.agent_id}
                  </span>
                </div>
              )}

              <div
                className="px-3.5 py-2.5 text-[13px] leading-relaxed"
                style={isOutbound ? {
                  background: 'rgba(90, 114, 240, 0.12)',
                  border: '1px solid rgba(90, 114, 240, 0.15)',
                  borderRadius: '12px 12px 4px 12px',
                  color: 'var(--text-primary)',
                } : {
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: '12px 12px 12px 4px',
                  color: 'var(--text-primary)',
                }}
              >
                {msg.content}
              </div>

              <div className={`flex items-center gap-2 mt-1 text-[10px] ${isOutbound ? 'justify-end' : ''}`} style={{ color: 'var(--text-tertiary)' }}>
                <span>{format(new Date(msg.created_at), 'MMM d, h:mm a')}</span>
                {isOutbound && msg.delivery_status && (
                  <span style={{
                    color: msg.delivery_status === 'delivered' ? '#34d399' :
                           msg.delivery_status === 'failed' ? '#f87171' : 'var(--text-tertiary)'
                  }}>
                    {msg.delivery_status === 'delivered' ? '\u2713\u2713' :
                     msg.delivery_status === 'sent' ? '\u2713' :
                     msg.delivery_status === 'failed' ? '\u2717' : ''}
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
