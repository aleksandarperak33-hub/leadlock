import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Save, Check, AlertCircle } from 'lucide-react';

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [config, setConfig] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const data = await api.getSettings();
        setSettings(data);
        setConfig(data.config || {});
      } catch (e) {
        console.error('Failed to fetch settings:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchSettings();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.updateSettings({ config });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const updateConfig = (path, value) => {
    setConfig(prev => {
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

  const inputClasses = 'w-full px-4 py-2.5 rounded-lg text-sm bg-white border border-gray-200 text-gray-900 placeholder-gray-400 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all';
  const labelClasses = 'block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5';

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-xl font-semibold tracking-tight text-gray-900">Settings</h1>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 transition-colors cursor-pointer shadow-sm"
        >
          {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {saved ? 'Saved' : saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>

      {error && (
        <div className="mb-5 px-4 py-3 rounded-lg flex items-center gap-2.5 text-sm bg-red-50 border border-red-100 text-red-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      <div className="space-y-5">
        {/* Business Info */}
        <section className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-5">Business Information</h2>
          <div className="grid grid-cols-2 gap-5">
            {[
              { label: 'Business Name', value: settings?.business_name },
              { label: 'Trade Type', value: settings?.trade_type, capitalize: true },
              { label: 'Twilio Number', value: settings?.twilio_phone || 'Not assigned' },
              { label: '10DLC Status', value: settings?.ten_dlc_status || 'pending', capitalize: true },
            ].map(({ label, value, capitalize }) => (
              <div key={label}>
                <span className="text-xs text-gray-400">{label}</span>
                <p className={`text-sm mt-0.5 font-medium ${capitalize ? 'capitalize' : ''} text-gray-900`}>{value || '\u2014'}</p>
              </div>
            ))}
          </div>
        </section>

        {/* AI Persona */}
        <section className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-5">AI Persona</h2>
          <div className="space-y-4">
            <div>
              <label className={labelClasses}>Rep Name</label>
              <input
                type="text"
                value={persona.rep_name || ''}
                onChange={e => updateConfig('persona.rep_name', e.target.value)}
                className={inputClasses}
              />
            </div>
            <div>
              <label className={labelClasses}>Tone</label>
              <select
                value={persona.tone || 'friendly_professional'}
                onChange={e => updateConfig('persona.tone', e.target.value)}
                className={`${inputClasses} cursor-pointer`}
              >
                <option value="friendly_professional">Friendly Professional</option>
                <option value="casual">Casual</option>
                <option value="formal">Formal</option>
              </select>
            </div>
            <div>
              <label className={labelClasses}>Emergency Contact Phone</label>
              <input
                type="text"
                value={persona.emergency_contact_phone || ''}
                onChange={e => updateConfig('persona.emergency_contact_phone', e.target.value)}
                className={inputClasses}
                placeholder="+15551234567"
              />
            </div>
          </div>
        </section>

        {/* Business Hours */}
        <section className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-5">Business Hours</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelClasses}>Weekday Start</label>
              <input
                type="time"
                value={hours.business?.start || '07:00'}
                onChange={e => updateConfig('hours.business.start', e.target.value)}
                className={inputClasses}
              />
            </div>
            <div>
              <label className={labelClasses}>Weekday End</label>
              <input
                type="time"
                value={hours.business?.end || '18:00'}
                onChange={e => updateConfig('hours.business.end', e.target.value)}
                className={inputClasses}
              />
            </div>
          </div>
          <div className="mt-4">
            <label className={labelClasses}>After Hours Handling</label>
            <select
              value={hours.after_hours_handling || 'ai_responds_books_next_available'}
              onChange={e => updateConfig('hours.after_hours_handling', e.target.value)}
              className={`${inputClasses} cursor-pointer`}
            >
              <option value="ai_responds_books_next_available">AI responds, books next available</option>
              <option value="ai_responds_owner_notified">AI responds, owner notified</option>
              <option value="do_not_respond">Do not respond until business hours</option>
            </select>
          </div>
        </section>

        {/* Services */}
        <section className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-5">Services</h2>
          <div className="space-y-4">
            {[
              { label: 'Primary Services', key: 'services.primary', val: services.primary },
              { label: 'Secondary Services', key: 'services.secondary', val: services.secondary },
              { label: 'Do Not Quote', key: 'services.do_not_quote', val: services.do_not_quote },
            ].map(({ label, key, val }) => (
              <div key={key}>
                <label className={labelClasses}>
                  {label} <span className="normal-case text-[10px] text-gray-400">(comma-separated)</span>
                </label>
                <input
                  type="text"
                  value={(val || []).join(', ')}
                  onChange={e => updateConfig(key, e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  className={inputClasses}
                />
              </div>
            ))}
          </div>
        </section>

        {/* Emergency Keywords */}
        <section className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-5">Custom Emergency Keywords</h2>
          <input
            type="text"
            value={(config.emergency_keywords || []).join(', ')}
            onChange={e => updateConfig('emergency_keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
            className={inputClasses}
            placeholder="gas leak, no heat, flooding..."
          />
          <p className="text-[11px] text-gray-400 mt-2.5">
            Default keywords (always active): gas leak, carbon monoxide, fire, flooding, burst pipe, no heat, no ac, sewage, exposed wires
          </p>
        </section>
      </div>
    </div>
  );
}
