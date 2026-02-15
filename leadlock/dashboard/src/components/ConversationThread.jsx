import { format } from 'date-fns';
import { Bot, MessageSquare } from 'lucide-react';

const AGENT_LABELS = {
  intake: 'Intake Agent',
  qualify: 'Qualify Agent',
  book: 'Book Agent',
  followup: 'Follow-Up Agent',
};

export default function ConversationThread({ messages = [] }) {
  if (!messages.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <MessageSquare className="w-10 h-10 mb-3" />
        <p>No messages yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 py-4">
      {messages.map((msg) => {
        const isOutbound = msg.direction === 'outbound';
        return (
          <div key={msg.id} className={`flex ${isOutbound ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%]`}>
              {isOutbound && msg.agent_id && (
                <div className="flex items-center gap-1 mb-1 justify-end">
                  <Bot className="w-3 h-3 text-brand-400" />
                  <span className="text-[10px] text-brand-400 font-medium">
                    {AGENT_LABELS[msg.agent_id] || msg.agent_id}
                  </span>
                </div>
              )}

              <div className={`
                px-4 py-2.5 rounded-2xl text-sm leading-relaxed
                ${isOutbound
                  ? 'bg-brand-600 text-white rounded-br-md'
                  : 'bg-slate-800 text-slate-100 rounded-bl-md'
                }
              `}>
                {msg.content}
              </div>

              <div className={`flex items-center gap-2 mt-1 text-[10px] text-slate-500 ${isOutbound ? 'justify-end' : ''}`}>
                <span>{format(new Date(msg.created_at), 'MMM d, h:mm a')}</span>
                {isOutbound && msg.delivery_status && (
                  <span className={
                    msg.delivery_status === 'delivered' ? 'text-emerald-500' :
                    msg.delivery_status === 'failed' ? 'text-red-500' : ''
                  }>
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
