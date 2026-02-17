import { useState, useEffect } from 'react';
import {
  Calendar,
  Clock,
  CheckCircle2,
  AlertCircle,
  User,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { api } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import StatCard from '../components/ui/StatCard';
import Tabs from '../components/ui/Tabs';
import Badge from '../components/ui/Badge';
import StatusDot from '../components/ui/StatusDot';
import EmptyState from '../components/ui/EmptyState';

const STATUS_BADGE_VARIANT = {
  confirmed: 'success',
  pending: 'warning',
  cancelled: 'danger',
  completed: 'info',
};

const CALENDAR_DOT_COLORS = {
  confirmed: 'bg-emerald-500',
  pending: 'bg-amber-500',
  cancelled: 'bg-red-500',
  completed: 'bg-blue-500',
};

const VIEW_TABS = [
  { id: 'list', label: 'List' },
  { id: 'calendar', label: 'Calendar' },
];

export default function Bookings() {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [view, setView] = useState('list');

  useEffect(() => {
    loadBookings();
  }, []);

  const loadBookings = async () => {
    try {
      const data = await api.getBookings();
      setBookings(data.bookings || []);
      setError(null);
    } catch (err) {
      console.error('Failed to load bookings:', err);
      setError(err.message || 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const today = new Date().toISOString().split('T')[0];
  const upcomingBookings = bookings.filter(
    (b) => b.appointment_date >= today && b.status !== 'cancelled'
  );
  const pastBookings = bookings.filter(
    (b) => b.appointment_date < today || b.status === 'cancelled'
  );

  const confirmedCount = bookings.filter((b) => b.status === 'confirmed').length;
  const pendingCount = bookings.filter((b) => b.status === 'pending').length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Bookings" />

      {error && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-red-600 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          Failed to load bookings data. <button onClick={() => { setError(null); loadBookings(); }} className="underline font-medium cursor-pointer">Retry</button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
        <StatCard
          label="Total Bookings"
          value={bookings.length}
          icon={Calendar}
          color="brand"
        />
        <StatCard
          label="Upcoming"
          value={upcomingBookings.length}
          icon={Clock}
          color="green"
        />
        <StatCard
          label="Confirmed"
          value={confirmedCount}
          icon={CheckCircle2}
          color="green"
        />
        <StatCard
          label="Pending"
          value={pendingCount}
          icon={AlertCircle}
          color="yellow"
        />
      </div>

      <Tabs tabs={VIEW_TABS} activeId={view} onChange={setView} />

      {view === 'list' && (
        <BookingList
          upcoming={upcomingBookings}
          past={pastBookings}
          total={bookings.length}
        />
      )}

      {view === 'calendar' && <CalendarGrid bookings={bookings} />}
    </div>
  );
}

function BookingList({ upcoming, past, total }) {
  if (total === 0) {
    return (
      <EmptyState
        icon={Calendar}
        title="No bookings yet"
        description="Bookings will appear here when leads are scheduled."
      />
    );
  }

  return (
    <div>
      {upcoming.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
            Upcoming
          </h2>
          <div className="space-y-3">
            {upcoming.map((b) => (
              <BookingCard key={b.id} booking={b} />
            ))}
          </div>
        </div>
      )}
      {past.length > 0 && (
        <div>
          <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
            Past
          </h2>
          <div className="space-y-3">
            {past.map((b) => (
              <BookingCard key={b.id} booking={b} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function BookingCard({ booking }) {
  const date = new Date(booking.appointment_date);
  const variant = STATUS_BADGE_VARIANT[booking.status] || 'neutral';
  const syncColor = booking.crm_sync_status === 'synced' ? 'green' : 'yellow';
  const syncLabel = booking.crm_sync_status === 'synced' ? 'Synced' : 'Pending sync';

  return (
    <div className="flex items-center gap-4 bg-white border border-gray-200/60 rounded-xl p-5 hover:bg-gray-50/50 transition-colors cursor-pointer">
      <div className="text-center w-14 flex-shrink-0">
        <p className="text-[10px] font-semibold uppercase text-gray-400">
          {date.toLocaleDateString('en-US', { month: 'short' })}
        </p>
        <p className="text-2xl font-bold font-mono leading-tight text-gray-900">
          {date.getDate()}
        </p>
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium truncate text-gray-900">
            {booking.service_type || 'Service appointment'}
          </p>
          <Badge variant={variant} size="sm">
            {booking.status}
          </Badge>
        </div>
        <div className="flex items-center gap-3 mt-1.5">
          {booking.time_window_start && (
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <Clock className="w-3 h-3" />
              <span className="font-mono">
                {booking.time_window_start} - {booking.time_window_end || '\u2014'}
              </span>
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
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <StatusDot color={syncColor} />
          <span className="text-xs text-gray-400">{syncLabel}</span>
        </div>
      )}
    </div>
  );
}

function CalendarGrid({ bookings }) {
  const [calendarDate, setCalendarDate] = useState(new Date());
  const today = new Date();

  const year = calendarDate.getFullYear();
  const month = calendarDate.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const bookingsByDate = {};
  bookings.forEach((b) => {
    const dateStr = b.appointment_date;
    if (!bookingsByDate[dateStr]) bookingsByDate[dateStr] = [];
    bookingsByDate[dateStr].push(b);
  });

  const days = [];
  for (let i = 0; i < firstDay; i++) days.push(null);
  for (let d = 1; d <= daysInMonth; d++) days.push(d);

  const monthLabel = calendarDate.toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });

  const goToPrevMonth = () => {
    setCalendarDate(new Date(year, month - 1, 1));
  };

  const goToNextMonth = () => {
    setCalendarDate(new Date(year, month + 1, 1));
  };

  const isToday = (day) =>
    day === today.getDate() &&
    month === today.getMonth() &&
    year === today.getFullYear();

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-5">
        <button
          onClick={goToPrevMonth}
          className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
        >
          <ChevronLeft className="w-4 h-4 text-gray-500" />
        </button>
        <p className="text-sm font-semibold text-gray-900">{monthLabel}</p>
        <button
          onClick={goToNextMonth}
          className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
        >
          <ChevronRight className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      <div className="grid grid-cols-7">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
          <div
            key={d}
            className="text-center text-[10px] font-medium uppercase tracking-wider py-2 text-gray-400"
          >
            {d}
          </div>
        ))}
        {days.map((day, i) => {
          if (!day) return <div key={`empty-${i}`} className="border border-gray-100 min-h-[80px]" />;

          const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const dayBookings = bookingsByDate[dateStr] || [];
          const todayCell = isToday(day);

          return (
            <div
              key={day}
              className={`border border-gray-100 min-h-[80px] p-1.5 ${
                todayCell ? 'bg-orange-50/50 border-orange-200' : ''
              }`}
            >
              <p
                className={`text-sm font-medium mb-1 ${
                  todayCell ? 'text-orange-600' : 'text-gray-600'
                }`}
              >
                {day}
              </p>
              <div className="flex items-center gap-1 flex-wrap">
                {dayBookings.map((b) => {
                  const dotColor = CALENDAR_DOT_COLORS[b.status] || 'bg-gray-300';
                  return (
                    <span
                      key={b.id}
                      className={`w-[6px] h-[6px] rounded-full ${dotColor}`}
                      title={`${b.service_type || 'Appointment'} (${b.status})`}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
