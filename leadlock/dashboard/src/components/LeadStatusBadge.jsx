import Badge from './ui/Badge';

/**
 * Status-to-variant mapping for the Badge component.
 */
const STATUS_VARIANT = {
  new: 'info',
  intake_sent: 'info',
  qualifying: 'warning',
  qualified: 'success',
  booking: 'warning',
  booked: 'success',
  follow_up: 'info',
  completed: 'success',
  cold: 'neutral',
  dead: 'neutral',
  opted_out: 'danger',
};

/**
 * Status-to-label mapping for display text.
 */
const STATUS_LABEL = {
  new: 'New',
  intake_sent: 'Intake Sent',
  qualifying: 'Qualifying',
  qualified: 'Qualified',
  booking: 'Booking',
  booked: 'Booked',
  follow_up: 'Follow-Up',
  completed: 'Completed',
  cold: 'Cold',
  dead: 'Dead',
  opted_out: 'Opted Out',
};

/**
 * LeadStatusBadge -- Renders a lead status as a color-coded Badge.
 *
 * @param {string} status - The lead status key
 */
export default function LeadStatusBadge({ status }) {
  const variant = STATUS_VARIANT[status] || 'neutral';
  const label = STATUS_LABEL[status] || status || 'Unknown';

  return (
    <Badge variant={variant} size="sm">
      {label}
    </Badge>
  );
}
