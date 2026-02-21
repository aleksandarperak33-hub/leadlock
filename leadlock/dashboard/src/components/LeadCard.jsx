import { formatDistanceToNow } from 'date-fns';
import LeadStatusBadge from './LeadStatusBadge';
import { Clock, MessageSquare } from 'lucide-react';
import { responseTimeHex } from '../lib/response-time';

export default function LeadCard({ lead, onClick }) {
  return (
    <div
      onClick={onClick}
      className="glass-card p-4 cursor-pointer group card-hover-lift"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-[13px] font-medium text-gray-900">
            {lead.first_name || 'Unknown'} {lead.last_name || ''}
          </p>
          <p className="text-[11px] font-mono mt-0.5 text-gray-400">{lead.phone_masked}</p>
        </div>
        <LeadStatusBadge status={lead.state} />
      </div>

      <div className="flex items-center gap-4 text-[12px] text-gray-400">
        {lead.service_type && (
          <span className="truncate max-w-[120px]">{lead.service_type}</span>
        )}
        {lead.first_response_ms && (
          <span
            className="flex items-center gap-1 font-mono"
            style={{ color: responseTimeHex(lead.first_response_ms) }}
          >
            <Clock className="w-3 h-3" />
            {(lead.first_response_ms / 1000).toFixed(1)}s
          </span>
        )}
        <span className="flex items-center gap-1">
          <MessageSquare className="w-3 h-3" />
          {lead.total_messages}
        </span>
      </div>

      <div className="flex items-center justify-between mt-3 text-[10px] text-gray-400">
        <span className="capitalize">{lead.source?.replace('_', ' ')}</span>
        <span>{formatDistanceToNow(new Date(lead.created_at), { addSuffix: true })}</span>
      </div>
    </div>
  );
}
