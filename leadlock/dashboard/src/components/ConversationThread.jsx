import { format } from 'date-fns';
import { MessageSquare } from 'lucide-react';
import Badge from './ui/Badge';

/**
 * Agent ID to display label mapping.
 */
const AGENT_LABELS = {
  intake: 'Intake',
  qualify: 'Qualify',
  book: 'Book',
  followup: 'Follow-Up',
};

/**
 * ConversationThread -- Renders a list of messages as a chat thread.
 * Outbound messages align right with orange styling, inbound align left with gray.
 *
 * @param {Array} messages - Array of message objects with direction, content, created_at, etc.
 */
export default function ConversationThread({ messages = [] }) {
  if (!messages.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-gray-400">
        <MessageSquare className="w-8 h-8 mb-3" strokeWidth={1.5} />
        <p className="text-sm">No messages yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 py-4">
      {messages.map((msg) => {
        const isOutbound = msg.direction === 'outbound';

        return (
          <div
            key={msg.id}
            className={`flex ${isOutbound ? 'justify-end' : 'justify-start'}`}
          >
            <div className="max-w-[75%]">
              {isOutbound && msg.agent_id && (
                <div className="flex items-center gap-1 mb-1 justify-end">
                  <Badge variant="neutral" size="sm">
                    {AGENT_LABELS[msg.agent_id] || msg.agent_id}
                  </Badge>
                </div>
              )}

              <div
                className={`px-4 py-3 text-sm leading-relaxed ${
                  isOutbound
                    ? 'bg-orange-50 border border-orange-100 rounded-2xl rounded-br-sm text-gray-900'
                    : 'bg-gray-50 border border-gray-100 rounded-2xl rounded-bl-sm text-gray-900'
                }`}
              >
                {msg.content || '(empty message)'}
              </div>

              <div
                className={`flex items-center gap-2 mt-1.5 text-xs text-gray-400 ${
                  isOutbound ? 'justify-end' : ''
                }`}
              >
                <span>
                  {msg.created_at ? format(new Date(msg.created_at), 'MMM d, h:mm a') : '\u2014'}
                </span>
                {isOutbound && msg.delivery_status && (
                  <span
                    className={
                      msg.delivery_status === 'delivered'
                        ? 'text-emerald-500'
                        : msg.delivery_status === 'failed'
                        ? 'text-red-500'
                        : 'text-gray-400'
                    }
                  >
                    {msg.delivery_status === 'delivered'
                      ? '\u2713\u2713'
                      : msg.delivery_status === 'sent'
                      ? '\u2713'
                      : msg.delivery_status === 'failed'
                      ? '\u2717'
                      : ''}
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
