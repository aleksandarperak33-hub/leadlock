import { useState, useEffect } from 'react';
import { Calendar, Clock, CheckCircle, AlertCircle, User } from 'lucide-react';
import { api } from '../api/client';

const STATUS_COLORS = {
  confirmed: { bg: 'rgba(52, 211, 153, 0.1)', text: '#34d399', border: 'rgba(52, 211, 153, 0.2)' },
  pending: { bg: 'rgba(251, 191, 36, 0.1)', text: '#fbbf24', border: 'rgba(251, 191, 36, 0.2)' },
  completed: { bg: 'rgba(96, 165, 250, 0.1)', text: '#60a5fa', border: 'rgba(96, 165, 250, 0.2)' },
  cancelled: { bg: 'rgba(248, 113, 113, 0.1)', text: '#f87171', border: 'rgba(248, 113, 113, 0.2)' },
};

function StatusBadge({ status }) {
  const colors = STATUS_COLORS[status] || STATUS_COLORS.pending;
  return (
    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium capitalize"
      style={{ background: colors.bg, color: colors.text, border: `1px solid ${colors.border}` }}>
      {status}
    </span>
  );
}

export default function Bookings() {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('list');

  useEffect(() => {
    loadBookings();
  }, []);

  const loadBookings = async () => {
    try {
      const data = await api.getBookings();
      setBookings(data.bookings || []);
    } catch (err) {
      console.error('Failed to load bookings:', err);
    } finally {
      setLoading(false);
    }
  };

  const upcomingBookings = bookings.filter(b => {
    const date = new Date(b.appointment_date);
    return date >= new Date() && b.status !== 'cancelled';
  });

  const pastBookings = bookings.filter(b => {
    const date = new Date(b.appointment_date);
    return date < new Date() || b.status === 'cancelled';
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }} />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-[20px] font-bold" style={{ color: 'var(--text-primary)' }}>Bookings</h1>
          <p className="text-[13px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
            {upcomingBookings.length} upcoming, {bookings.length} total
          </p>
        </div>
        <div className="flex gap-1 rounded-lg p-0.5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          {['list', 'calendar'].map(v => (
            <button key={v} onClick={() => setView(v)}
              className="px-3 py-1.5 rounded-md text-[12px] font-medium capitalize transition-all"
              style={{
                background: view === v ? 'var(--accent-muted)' : 'transparent',
                color: view === v ? 'var(--accent)' : 'var(--text-tertiary)',
              }}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'Total Bookings', value: bookings.length, icon: Calendar },
          { label: 'Upcoming', value: upcomingBookings.length, icon: Clock, color: '#60a5fa' },
          { label: 'Confirmed', value: bookings.filter(b => b.status === 'confirmed').length, icon: CheckCircle, color: '#34d399' },
          { label: 'Pending', value: bookings.filter(b => b.status === 'pending').length, icon: AlertCircle, color: '#fbbf24' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="rounded-xl p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <div className="flex items-center gap-2 mb-2">
              <Icon className="w-3.5 h-3.5" style={{ color: color || 'var(--text-tertiary)' }} />
              <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
            </div>
            <p className="text-[22px] font-bold" style={{ color: color || 'var(--text-primary)' }}>{value}</p>
          </div>
        ))}
      </div>

      {/* Bookings list */}
      {view === 'list' && (
        <div>
          {upcomingBookings.length > 0 && (
            <div className="mb-6">
              <h2 className="text-[13px] font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>Upcoming</h2>
              <div className="space-y-2">
                {upcomingBookings.map(b => (
                  <BookingCard key={b.id} booking={b} />
                ))}
              </div>
            </div>
          )}
          {pastBookings.length > 0 && (
            <div>
              <h2 className="text-[13px] font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>Past</h2>
              <div className="space-y-2">
                {pastBookings.map(b => (
                  <BookingCard key={b.id} booking={b} />
                ))}
              </div>
            </div>
          )}
          {bookings.length === 0 && (
            <div className="text-center py-16">
              <Calendar className="w-10 h-10 mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }} />
              <p className="text-[14px] font-medium" style={{ color: 'var(--text-secondary)' }}>No bookings yet</p>
              <p className="text-[12px] mt-1" style={{ color: 'var(--text-tertiary)' }}>Bookings will appear here when leads are scheduled.</p>
            </div>
          )}
        </div>
      )}

      {/* Simple calendar grid */}
      {view === 'calendar' && (
        <CalendarGrid bookings={bookings} />
      )}
    </div>
  );
}

function BookingCard({ booking }) {
  const date = new Date(booking.appointment_date);
  return (
    <div className="flex items-center gap-4 rounded-xl p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      <div className="text-center w-14 flex-shrink-0">
        <p className="text-[10px] font-semibold uppercase" style={{ color: 'var(--text-tertiary)' }}>
          {date.toLocaleDateString('en-US', { month: 'short' })}
        </p>
        <p className="text-[22px] font-bold leading-tight" style={{ color: 'var(--text-primary)' }}>
          {date.getDate()}
        </p>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-[13px] font-medium truncate" style={{ color: 'var(--text-primary)' }}>
            {booking.service_type || 'Service appointment'}
          </p>
          <StatusBadge status={booking.status} />
        </div>
        <div className="flex items-center gap-3 mt-1">
          {booking.time_window_start && (
            <span className="flex items-center gap-1 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
              <Clock className="w-3 h-3" />
              {booking.time_window_start} - {booking.time_window_end}
            </span>
          )}
          {booking.tech_name && (
            <span className="flex items-center gap-1 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
              <User className="w-3 h-3" />
              {booking.tech_name}
            </span>
          )}
        </div>
      </div>
      {booking.crm_sync_status && (
        <span className="text-[10px] px-1.5 py-0.5 rounded" style={{
          background: booking.crm_sync_status === 'synced' ? 'rgba(52, 211, 153, 0.1)' : 'rgba(251, 191, 36, 0.1)',
          color: booking.crm_sync_status === 'synced' ? '#34d399' : '#fbbf24',
        }}>
          {booking.crm_sync_status}
        </span>
      )}
    </div>
  );
}

function CalendarGrid({ bookings }) {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const bookingsByDate = {};
  bookings.forEach(b => {
    const dateStr = b.appointment_date;
    if (!bookingsByDate[dateStr]) bookingsByDate[dateStr] = [];
    bookingsByDate[dateStr].push(b);
  });

  const days = [];
  for (let i = 0; i < firstDay; i++) days.push(null);
  for (let d = 1; d <= daysInMonth; d++) days.push(d);

  const monthStr = now.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      <p className="text-[14px] font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>{monthStr}</p>
      <div className="grid grid-cols-7 gap-1">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
          <div key={d} className="text-center text-[10px] font-semibold uppercase py-1" style={{ color: 'var(--text-tertiary)' }}>{d}</div>
        ))}
        {days.map((day, i) => {
          if (!day) return <div key={`empty-${i}`} />;
          const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const dayBookings = bookingsByDate[dateStr] || [];
          const isToday = day === now.getDate();
          return (
            <div key={day} className="rounded-lg p-1.5 min-h-[60px]" style={{
              background: isToday ? 'var(--accent-muted)' : 'transparent',
              border: isToday ? '1px solid rgba(124, 91, 240, 0.2)' : '1px solid transparent',
            }}>
              <p className="text-[11px] font-medium" style={{ color: isToday ? 'var(--accent)' : 'var(--text-secondary)' }}>{day}</p>
              {dayBookings.map(b => (
                <div key={b.id} className="mt-0.5 px-1 py-0.5 rounded text-[9px] truncate"
                  style={{ background: STATUS_COLORS[b.status]?.bg || 'var(--surface-2)', color: STATUS_COLORS[b.status]?.text || 'var(--text-secondary)' }}>
                  {b.service_type || 'Appt'}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
