import { SectionHeader } from './SectionHeader';
import { INPUT_CLASSES } from './constants';

export default function EmergencyKeywordsSection({ config, updateConfig }) {
  return (
    <div>
      <SectionHeader
        title="Emergency Keywords"
        description="Custom keywords that trigger emergency routing."
      />
      <label htmlFor="emergency-keywords" className="sr-only">Emergency keywords</label>
      <input
        id="emergency-keywords"
        type="text"
        value={(config.emergency_keywords || []).join(', ')}
        onChange={(e) =>
          updateConfig(
            'emergency_keywords',
            e.target.value
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean)
          )
        }
        className={INPUT_CLASSES}
        placeholder="gas leak, no heat, flooding..."
      />
      <p className="text-xs text-gray-400 mt-2.5">
        Default keywords (always active): gas leak, carbon monoxide, fire,
        flooding, burst pipe, no heat, no ac, sewage, exposed wires
      </p>
    </div>
  );
}
