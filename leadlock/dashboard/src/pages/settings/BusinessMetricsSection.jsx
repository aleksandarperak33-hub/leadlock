import { SectionHeader } from './SectionHeader';
import { INPUT_CLASSES, LABEL_CLASSES } from './constants';

export default function BusinessMetricsSection({ config, updateConfig }) {
  return (
    <div>
      <SectionHeader
        title="Business Metrics"
        description="Set your booking link and average job value for ROI tracking."
      />
      <div className="space-y-5">
        <div>
          <label htmlFor="booking-url" className={LABEL_CLASSES}>Booking URL</label>
          <input
            id="booking-url"
            type="url"
            value={config.booking_url || ''}
            onChange={(e) => updateConfig('booking_url', e.target.value)}
            className={INPUT_CLASSES}
            placeholder="https://calendly.com/your-business"
          />
          <p className="mt-1.5 text-xs text-gray-400">
            Used in SMS messages so leads can self-book appointments.
          </p>
        </div>
        <div>
          <label htmlFor="avg-job-value" className={LABEL_CLASSES}>Average Job Value ($)</label>
          <input
            id="avg-job-value"
            type="number"
            min="0"
            step="1"
            value={config.avg_job_value ?? ''}
            onChange={(e) => {
              const raw = e.target.value;
              updateConfig('avg_job_value', raw === '' ? null : parseFloat(raw));
            }}
            className={INPUT_CLASSES}
            placeholder="e.g. 1500"
          />
          <p className="mt-1.5 text-xs text-gray-400">
            Estimated revenue per booked job. Powers the ROI dashboard calculations.
          </p>
        </div>
      </div>
    </div>
  );
}
