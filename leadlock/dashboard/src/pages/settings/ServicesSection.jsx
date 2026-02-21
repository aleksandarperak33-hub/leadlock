import { SectionHeader } from './SectionHeader';
import { INPUT_CLASSES, LABEL_CLASSES } from './constants';

export default function ServicesSection({ services, updateConfig }) {
  const serviceFields = [
    { label: 'Primary Services', key: 'services.primary', val: services.primary, id: 'primary-services' },
    { label: 'Secondary Services', key: 'services.secondary', val: services.secondary, id: 'secondary-services' },
    { label: 'Do Not Quote', key: 'services.do_not_quote', val: services.do_not_quote, id: 'do-not-quote' },
  ];

  return (
    <div>
      <SectionHeader
        title="Services"
        description="Define which services you offer and which to avoid quoting."
      />
      <div className="space-y-5">
        {serviceFields.map(({ label, key, val, id }) => (
          <div key={key}>
            <label htmlFor={id} className={LABEL_CLASSES}>
              {label}{' '}
              <span className="font-normal text-xs text-gray-400">
                (comma-separated)
              </span>
            </label>
            <input
              id={id}
              type="text"
              value={(val || []).join(', ')}
              onChange={(e) =>
                updateConfig(
                  key,
                  e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)
                )
              }
              className={INPUT_CLASSES}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
