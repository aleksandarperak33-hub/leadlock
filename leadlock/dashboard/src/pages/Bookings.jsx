import { useState, useEffect } from 'react';
import { Calendar, Clock, CheckCircle, AlertCircle, User } from 'lucide-react';
import { api } from '../api/client';

const STATUS_STYLES = {
  confirmed: { badge: 'bg-emerald-50 text-emerald-700 border border-emerald-100', dot: 'bg-emerald-500' },
  pending: { badge: 'bg-amber-50 text-amber-700 border border-amber-100', dot: 'bg-amber-500' },
  completed: { badge: 'bg-blue-50 text-blue-700 border border-blue-100', dot: 'bg-blue-500' },
  cancelled: { badge: 'bg-red-50 text-red-700 border border-red-100', dot: 'bg-red-500' },
};

const CALENDAR_STATUS_COLORS = {
  confirmed: { bg: 'bg-emerald-50', text: 'text-emerald-700' },
  pending: { bg: 'bg-amber-50', text: 'text-amber-700' },
  completed: { bg: 'bg-blue-50', text: 'text-blue-700' },
  cancelled: { bg: 'bg-red-50', text: 'text-red-700' },
};

function StatusBadge({ status }) {
  const styles = STATUS_STYLES[status] || STATUS_STYLES.pending;
  return (
    <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium capitalize ${styles.badge}`}>
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
        <div className="w-6 h-6 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">Bookings</h1>
          <p className="text-sm text-gray-500 mt-1">
            {upcomingBookings.length} upcoming, {bookings.length} total
          </p>
        </div>
        <div className="flex gap-1 rounded-lg p-1 bg-gray-100 border border-gray-200">
          {['list', 'calendar'].map(v => (
            <button key={v} onClick={() => setView(v)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-all cursor-pointer ${
                view === v
                  ? 'bg-white text-orange-600 shadow-sm border border-gray-200'
                  : 'text-gray-500 hover:text-gray-700'
              }`}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: 'Total Bookings', value: bookings.length, icon: Calendar, color: 'text-gray-900' },
          { label: 'Upcoming', value: upcomingBookings.length, icon: Clock, color: 'text-blue-600' },
          { label: 'Confirmed', value: bookings.filter(b => b.status === 'confirmed').length, icon: CheckCircle, color: 'text-emerald-600' },
          { label: 'Pending', value: bookings.filter(b => b.status === 'pending').length, icon: AlertCircle, color: 'text-amber-600' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
            <div className="flex items-center gap-2 mb-2">
              <Icon className={`w-4 h-4 ${color === 'text-gray-900' ? 'text-gray-400' : color}`} />
              <span className="text-xs font-medium uppercase tracking-wider text-gray-500">{label}</span>
            </div>
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Bookings list */}
      {view === 'list' && (
        <div>
          {upcomingBookings.length > 0 && (
            <div className="mb-8">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">Upcoming</h2>
              <div className="space-y-2">
                {upcomingBookings.map(b => (
                  <BookingCard key={b.id} booking={b} />
                ))}
              </div>
            </div>
          )}
          {pastBookings.length > 0 && (
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">Past</h2>
              <div className="space-y-2">
                {pastBookings.map(b => (
                  <BookingCard key={b.id} booking={b} />
                ))}
              </div>
            </div>
          )}
          {bookings.length === 0 && (
            <div className="text-center py-20">
              <Calendar className="w-10 h-10 mx-auto mb-3 text-gray-300" />
              <p className="text-sm font-medium text-gray-600">No bookings yet</p>
              <p className="text-xs text-gray-400 mt-1">Bookings will appear here when leads are scheduled.</p>
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
    <div className="flex items-center gap-4 bg-white border border-gray-200 rounded-xl shadow-sm p-4 hover:bg-gray-50 transition-colors">
      <div className="text-center w-14 flex-shrink-0">
        <p className="text-[10px] font-semibold uppercase text-gray-400">
          {date.toLocaleDateString('en-US', { month: 'short' })}
        </p>
        <p className="text-2xl font-bold leading-tight text-gray-900">
          {date.getDate()}
        </p>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium truncate text-gray-900">
            {booking.service_type || 'Service appointment'}
          </p>
          <StatusBadge status={booking.status} />
        </div>
        <div className="flex items-center gap-3 mt-1">
          {booking.time_window_start && (
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <Clock className="w-3 h-3" />
              {booking.time_window_start} - {booking.time_window_end}
            </span>
          )}
          {booking.tech_name && (
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <User className="w-3 h-3" />
              {booking.tech_name}
            </span>
          )}
        </div>
      </div>
      {booking.crm_sync_status && (
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${
          booking.crm_sync_status === 'synced'
            ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
            : 'bg-amber-50 text-amber-700 border-amber-100'
        }`}>
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
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
      <p className="text-sm font-semibold text-gray-900 mb-4">{monthStr}</p>
      <div className="grid grid-cols-7 gap-1">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
          <div key={d} className="text-center text-[10px] font-semibold uppercase py-1.5 text-gray-400">{d}</div>
        ))}
        {days.map((day, i) => {
          if (!day) return <div key={`empty-${i}`} />;
          const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const dayBookings = bookingsByDate[dateStr] || [];
          const isToday = day === now.getDate();
          return (
            <div key={day} className={`rounded-lg p-1.5 min-h-[60px] border ${
              isToday
                ? 'bg-orange-50 border-orange-200'
                : 'border-transparent hover:bg-gray-50'
            } transition-colors`}>
              <p className={`text-xs font-medium ${isToday ? 'text-orange-600' : 'text-gray-600'}`}>{day}</p>
              {dayBookings.map(b => {
                const colors = CALENDAR_STATUS_COLORS[b.status] || { bg: 'bg-gray-50', text: 'text-gray-600' };
                return (
                  <div key={b.id} className={`mt-0.5 px-1 py-0.5 rounded text-[9px] truncate ${colors.bg} ${colors.text}`}>
                    {b.service_type || 'Appt'}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
