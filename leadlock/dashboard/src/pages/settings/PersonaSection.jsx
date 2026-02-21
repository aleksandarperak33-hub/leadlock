import { SectionHeader } from './SectionHeader';
import { INPUT_CLASSES, LABEL_CLASSES, TONE_OPTIONS } from './constants';

export default function PersonaSection({ persona, updateConfig }) {
  return (
    <div>
      <SectionHeader
        title="AI Persona"
        description="Customize how LeadLock AI communicates with your leads."
      />
      <div className="space-y-5">
        <div>
          <label htmlFor="rep-name" className={LABEL_CLASSES}>Rep Name</label>
          <input
            id="rep-name"
            type="text"
            value={persona.rep_name || ''}
            onChange={(e) => updateConfig('persona.rep_name', e.target.value)}
            className={INPUT_CLASSES}
            placeholder="e.g. Sarah"
          />
        </div>
        <div>
          <label htmlFor="tone" className={LABEL_CLASSES}>Tone</label>
          <select
            id="tone"
            value={persona.tone || 'friendly_professional'}
            onChange={(e) => updateConfig('persona.tone', e.target.value)}
            className={`${INPUT_CLASSES} cursor-pointer`}
          >
            {TONE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="emergency-phone" className={LABEL_CLASSES}>Emergency Contact Phone</label>
          <input
            id="emergency-phone"
            type="text"
            value={persona.emergency_contact_phone || ''}
            onChange={(e) =>
              updateConfig('persona.emergency_contact_phone', e.target.value)
            }
            className={INPUT_CLASSES}
            placeholder="+15551234567"
          />
        </div>
      </div>
    </div>
  );
}
