import { X, Calendar, Clock, User, MapPin } from 'lucide-react';
import Badge from './ui/Badge';
import StatusDot from './ui/StatusDot';
import { format } from 'date-fns';

const STATUS_BADGE_VARIANT = {
  confirmed: 'success',
  pending: 'warning',
  cancelled: 'danger',
  completed: 'info',
};

export default function BookingDetailModal({ booking, onClose }) {
  if (!booking) return null;

  const date = new Date(booking.appointment_date);
  const variant = STATUS_BADGE_VARIANT[booking.status] || 'neutral';
  const syncColor = booking.crm_sync_status === 'synced' ? 'green' : 'yellow';
  const syncLabel = booking.crm_sync_status === 'synced' ? 'Synced to CRM' : 'Pending sync';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/20 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl max-w-md w-full border border-gray-200/50 animate-fade-up">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 className="text-base font-semibold text-gray-900">Booking Details</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 cursor-pointer"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          {/* Service + Status */}
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-gray-900">
              {booking.service_type || 'Service appointment'}
            </p>
            <Badge variant={variant} size="sm">
              {booking.status}
            </Badge>
          </div>

          {/* Date */}
          <div className="flex items-center gap-3 text-sm">
            <Calendar className="w-4 h-4 text-gray-400 flex-shrink-0" />
            <span className="text-gray-700">
              {format(date, 'EEEE, MMMM d, yyyy')}
            </span>
          </div>

          {/* Time */}
          {booking.time_window_start && (
            <div className="flex items-center gap-3 text-sm">
              <Clock className="w-4 h-4 text-gray-400 flex-shrink-0" />
              <span className="text-gray-700 font-mono">
                {booking.time_window_start}
                {booking.time_window_end ? ` - ${booking.time_window_end}` : ''}
              </span>
            </div>
          )}

          {/* Technician */}
          {booking.tech_name && (
            <div className="flex items-center gap-3 text-sm">
              <User className="w-4 h-4 text-gray-400 flex-shrink-0" />
              <span className="text-gray-700">{booking.tech_name}</span>
            </div>
          )}

          {/* Lead info */}
          {booking.lead_name && (
            <div className="flex items-center gap-3 text-sm">
              <User className="w-4 h-4 text-gray-400 flex-shrink-0" />
              <span className="text-gray-700">{booking.lead_name}</span>
              {booking.phone_masked && (
                <span className="text-gray-400 font-mono text-xs">{booking.phone_masked}</span>
              )}
            </div>
          )}

          {/* Address */}
          {booking.address && (
            <div className="flex items-center gap-3 text-sm">
              <MapPin className="w-4 h-4 text-gray-400 flex-shrink-0" />
              <span className="text-gray-700">{booking.address}</span>
            </div>
          )}

          {/* Notes */}
          {booking.notes && (
            <div className="bg-gray-50 rounded-xl p-3">
              <p className="text-xs font-medium text-gray-500 mb-1">Notes</p>
              <p className="text-sm text-gray-700">{booking.notes}</p>
            </div>
          )}

          {/* CRM Sync */}
          {booking.crm_sync_status && (
            <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
              <StatusDot color={syncColor} />
              <span className="text-xs text-gray-400">{syncLabel}</span>
              {booking.crm_job_id && (
                <span className="text-xs font-mono text-gray-400 ml-auto">
                  Job #{booking.crm_job_id}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 bg-gray-50/50 rounded-b-2xl">
          <button
            onClick={onClose}
            className="w-full px-4 py-2.5 rounded-xl text-sm font-medium text-gray-600 bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
