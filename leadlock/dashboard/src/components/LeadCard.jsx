import { formatDistanceToNow } from 'date-fns';
import LeadStatusBadge from './LeadStatusBadge';
import { Phone, Clock, MessageSquare } from 'lucide-react';

export default function LeadCard({ lead, onClick }) {
  const responseColor = !lead.first_response_ms ? 'text-slate-500' :
    lead.first_response_ms < 10000 ? 'text-emerald-400' :
    lead.first_response_ms < 60000 ? 'text-amber-400' : 'text-red-400';

  return (
    <div
      onClick={onClick}
      className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-colors cursor-pointer"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-sm font-medium text-white">
            {lead.first_name || 'Unknown'} {lead.last_name || ''}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">{lead.phone_masked}</p>
        </div>
        <LeadStatusBadge status={lead.state} />
      </div>

      <div className="flex items-center gap-4 text-xs text-slate-400">
        {lead.service_type && (
          <span className="truncate max-w-[120px]">{lead.service_type}</span>
        )}
        {lead.first_response_ms && (
          <span className={`flex items-center gap-1 ${responseColor}`}>
            <Clock className="w-3 h-3" />
            {(lead.first_response_ms / 1000).toFixed(1)}s
          </span>
        )}
        <span className="flex items-center gap-1">
          <MessageSquare className="w-3 h-3" />
          {lead.total_messages}
        </span>
      </div>

      <div className="flex items-center justify-between mt-3 text-[10px] text-slate-500">
        <span className="capitalize">{lead.source?.replace('_', ' ')}</span>
        <span>{formatDistanceToNow(new Date(lead.created_at), { addSuffix: true })}</span>
      </div>
    </div>
  );
}
