import { SectionHeader } from './SectionHeader';
import { INPUT_CLASSES, LABEL_CLASSES, AFTER_HOURS_OPTIONS } from './constants';

export default function BusinessHoursSection({ hours, updateConfig }) {
  return (
    <div>
      <SectionHeader
        title="Business Hours"
        description="Set your availability and after-hours behavior."
      />
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="weekday-start" className={LABEL_CLASSES}>Weekday Start</label>
            <input
              id="weekday-start"
              type="time"
              value={hours.business?.start || '07:00'}
              onChange={(e) =>
                updateConfig('hours.business.start', e.target.value)
              }
              className={INPUT_CLASSES}
            />
          </div>
          <div>
            <label htmlFor="weekday-end" className={LABEL_CLASSES}>Weekday End</label>
            <input
              id="weekday-end"
              type="time"
              value={hours.business?.end || '18:00'}
              onChange={(e) =>
                updateConfig('hours.business.end', e.target.value)
              }
              className={INPUT_CLASSES}
            />
          </div>
        </div>
        <div>
          <label htmlFor="after-hours" className={LABEL_CLASSES}>After Hours Handling</label>
          <select
            id="after-hours"
            value={hours.after_hours_handling || 'ai_responds_books_next_available'}
            onChange={(e) =>
              updateConfig('hours.after_hours_handling', e.target.value)
            }
            className={`${INPUT_CLASSES} cursor-pointer`}
          >
            {AFTER_HOURS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
