import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import { Save, Check, AlertCircle } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';

const INPUT_CLASSES =
  'w-full px-4 py-2.5 text-sm bg-white border border-gray-200 rounded-xl outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100 placeholder:text-gray-400 text-gray-900 transition-all';

const LABEL_CLASSES = 'text-sm font-medium text-gray-700 mb-1.5 block';

const TONE_OPTIONS = [
  { value: 'friendly_professional', label: 'Friendly Professional' },
  { value: 'casual', label: 'Casual' },
  { value: 'formal', label: 'Formal' },
];

const AFTER_HOURS_OPTIONS = [
  { value: 'ai_responds_books_next_available', label: 'AI responds, books next available' },
  { value: 'ai_responds_owner_notified', label: 'AI responds, owner notified' },
  { value: 'do_not_respond', label: 'Do not respond until business hours' },
];

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [config, setConfig] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const savedTimerRef = useRef(null);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const data = await api.getSettings();
        setSettings(data);
        setConfig(data.config || {});
        setLoadError(false);
      } catch (e) {
        console.error('Failed to fetch settings:', e);
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    };
    fetchSettings();
    return () => clearTimeout(savedTimerRef.current);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.updateSettings({ config });
      setSaved(true);
      clearTimeout(savedTimerRef.current);
      savedTimerRef.current = setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const updateConfig = (path, value) => {
    setConfig((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const keys = path.split('.');
      let obj = next;
      for (let i = 0; i < keys.length - 1; i++) {
        if (!obj[keys[i]]) obj[keys[i]] = {};
        obj = obj[keys[i]];
      }
      obj[keys[keys.length - 1]] = value;
      return next;
    });
  };

  if (loading) {
    return <div className="h-96 rounded-xl bg-gray-100 animate-pulse" />;
  }

  const persona = config.persona || {};
  const hours = config.hours || {};
  const services = config.services || {};

  const saveButton = (
    <button
      onClick={handleSave}
      disabled={saving || loadError}
      className="flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium px-6 py-2.5 rounded-xl disabled:opacity-50 transition-colors cursor-pointer"
    >
      {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
      {saved ? 'Saved' : saving ? 'Saving...' : 'Save Changes'}
    </button>
  );

  return (
    <div>
      <PageHeader title="Settings" actions={saveButton} />

      {loadError && (
        <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60 text-red-600 text-sm">
          Settings failed to load. Please refresh the page before making changes.
        </div>
      )}

      {error && (
        <div className="mb-6 px-4 py-3 rounded-xl flex items-center gap-2.5 text-sm bg-red-50 border border-red-200 text-red-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      <div className="max-w-2xl mx-auto">
        <BusinessInfoSection settings={settings} />

        <SectionDivider />

        <PersonaSection persona={persona} updateConfig={updateConfig} />

        <SectionDivider />

        <BusinessHoursSection hours={hours} updateConfig={updateConfig} />

        <SectionDivider />

        <ServicesSection services={services} updateConfig={updateConfig} />

        <SectionDivider />

        <EmergencyKeywordsSection config={config} updateConfig={updateConfig} />
      </div>
    </div>
  );
}

function SectionDivider() {
  return <div className="border-b border-gray-200/60 pb-8 mb-8" />;
}

function SectionHeader({ title, description }) {
  return (
    <div className="mb-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-1">{title}</h2>
      {description && (
        <p className="text-sm text-gray-500">{description}</p>
      )}
    </div>
  );
}

function BusinessInfoSection({ settings }) {
  const fields = [
    { label: 'Business Name', value: settings?.business_name },
    { label: 'Trade Type', value: settings?.trade_type, capitalize: true },
    { label: 'Twilio Number', value: settings?.twilio_phone || 'Not assigned' },
    { label: '10DLC Status', value: settings?.ten_dlc_status || 'pending', capitalize: true },
  ];

  return (
    <div>
      <SectionHeader
        title="Business Information"
        description="Read-only details about your account."
      />
      <div className="bg-gray-50 border border-gray-200/60 rounded-xl p-4">
        <div className="grid grid-cols-2 gap-5">
          {fields.map(({ label, value, capitalize }) => (
            <div key={label}>
              <span className="text-xs text-gray-400">{label}</span>
              <p
                className={`text-sm mt-0.5 font-medium text-gray-900 ${
                  capitalize ? 'capitalize' : ''
                }`}
              >
                {value || '\u2014'}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function PersonaSection({ persona, updateConfig }) {
  return (
    <div>
      <SectionHeader
        title="AI Persona"
        description="Customize how LeadLock AI communicates with your leads."
      />
      <div className="space-y-5">
        <div>
          <label className={LABEL_CLASSES}>Rep Name</label>
          <input
            type="text"
            value={persona.rep_name || ''}
            onChange={(e) => updateConfig('persona.rep_name', e.target.value)}
            className={INPUT_CLASSES}
            placeholder="e.g. Sarah"
          />
        </div>
        <div>
          <label className={LABEL_CLASSES}>Tone</label>
          <select
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
          <label className={LABEL_CLASSES}>Emergency Contact Phone</label>
          <input
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

function BusinessHoursSection({ hours, updateConfig }) {
  return (
    <div>
      <SectionHeader
        title="Business Hours"
        description="Set your availability and after-hours behavior."
      />
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASSES}>Weekday Start</label>
            <input
              type="time"
              value={hours.business?.start || '07:00'}
              onChange={(e) =>
                updateConfig('hours.business.start', e.target.value)
              }
              className={INPUT_CLASSES}
            />
          </div>
          <div>
            <label className={LABEL_CLASSES}>Weekday End</label>
            <input
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
          <label className={LABEL_CLASSES}>After Hours Handling</label>
          <select
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

function ServicesSection({ services, updateConfig }) {
  const serviceFields = [
    { label: 'Primary Services', key: 'services.primary', val: services.primary },
    { label: 'Secondary Services', key: 'services.secondary', val: services.secondary },
    { label: 'Do Not Quote', key: 'services.do_not_quote', val: services.do_not_quote },
  ];

  return (
    <div>
      <SectionHeader
        title="Services"
        description="Define which services you offer and which to avoid quoting."
      />
      <div className="space-y-5">
        {serviceFields.map(({ label, key, val }) => (
          <div key={key}>
            <label className={LABEL_CLASSES}>
              {label}{' '}
              <span className="font-normal text-xs text-gray-400">
                (comma-separated)
              </span>
            </label>
            <input
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

function EmergencyKeywordsSection({ config, updateConfig }) {
  return (
    <div>
      <SectionHeader
        title="Emergency Keywords"
        description="Custom keywords that trigger emergency routing."
      />
      <input
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
