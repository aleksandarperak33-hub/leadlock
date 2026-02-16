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
    return <div className="h-96 rounded-xl animate-pulse" style={{ background: 'var(--surface-1)' }} />;
  }

  const persona = config.persona || {};
  const hours = config.hours || {};
  const services = config.services || {};

  return (
    <div className="max-w-2xl animate-fade-up">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Settings</h1>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-[12px] font-semibold text-white gradient-btn disabled:opacity-50"
        >
          {saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
          {saved ? 'Saved' : saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-xl flex items-center gap-2.5 text-[13px]"
          style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.12)', color: '#f87171' }}>
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      <div className="space-y-4">
        {/* Business Info */}
        <section className="glass-card gradient-border p-5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>Business Information</h2>
          <div className="grid grid-cols-2 gap-4">
            {[
              { label: 'Business Name', value: settings?.business_name },
              { label: 'Trade Type', value: settings?.trade_type, capitalize: true },
              { label: 'Twilio Number', value: settings?.twilio_phone || 'Not assigned' },
              { label: '10DLC Status', value: settings?.ten_dlc_status || 'pending', capitalize: true },
            ].map(({ label, value, capitalize }) => (
              <div key={label}>
                <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
                <p className={`text-[13px] mt-0.5 ${capitalize ? 'capitalize' : ''}`} style={{ color: 'var(--text-primary)' }}>{value || '\u2014'}</p>
              </div>
            ))}
          </div>
        </section>

        {/* AI Persona */}
        <section className="glass-card gradient-border p-5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>AI Persona</h2>
          <div className="space-y-3.5">
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-tertiary)' }}>Rep Name</label>
              <input
                type="text"
                value={persona.rep_name || ''}
                onChange={e => updateConfig('persona.rep_name', e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
                style={{ color: 'var(--text-primary)' }}
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-tertiary)' }}>Tone</label>
              <select
                value={persona.tone || 'friendly_professional'}
                onChange={e => updateConfig('persona.tone', e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
                style={{ color: 'var(--text-primary)' }}
              >
                <option value="friendly_professional">Friendly Professional</option>
                <option value="casual">Casual</option>
                <option value="formal">Formal</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-tertiary)' }}>Emergency Contact Phone</label>
              <input
                type="text"
                value={persona.emergency_contact_phone || ''}
                onChange={e => updateConfig('persona.emergency_contact_phone', e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
                style={{ color: 'var(--text-primary)' }}
                placeholder="+15551234567"
              />
            </div>
          </div>
        </section>

        {/* Business Hours */}
        <section className="glass-card gradient-border p-5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>Business Hours</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-tertiary)' }}>Weekday Start</label>
              <input
                type="time"
                value={hours.business?.start || '07:00'}
                onChange={e => updateConfig('hours.business.start', e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
                style={{ color: 'var(--text-primary)' }}
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-tertiary)' }}>Weekday End</label>
              <input
                type="time"
                value={hours.business?.end || '18:00'}
                onChange={e => updateConfig('hours.business.end', e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
                style={{ color: 'var(--text-primary)' }}
              />
            </div>
          </div>
          <div className="mt-3.5">
            <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-tertiary)' }}>After Hours Handling</label>
            <select
              value={hours.after_hours_handling || 'ai_responds_books_next_available'}
              onChange={e => updateConfig('hours.after_hours_handling', e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
              style={{ color: 'var(--text-primary)' }}
            >
              <option value="ai_responds_books_next_available">AI responds, books next available</option>
              <option value="ai_responds_owner_notified">AI responds, owner notified</option>
              <option value="do_not_respond">Do not respond until business hours</option>
            </select>
          </div>
        </section>

        {/* Services */}
        <section className="glass-card gradient-border p-5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>Services</h2>
          <div className="space-y-3.5">
            {[
              { label: 'Primary Services', key: 'services.primary', val: services.primary },
              { label: 'Secondary Services', key: 'services.secondary', val: services.secondary },
              { label: 'Do Not Quote', key: 'services.do_not_quote', val: services.do_not_quote },
            ].map(({ label, key, val }) => (
              <div key={key}>
                <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-tertiary)' }}>
                  {label} <span className="normal-case text-[10px]" style={{ color: 'var(--text-tertiary)' }}>(comma-separated)</span>
                </label>
                <input
                  type="text"
                  value={(val || []).join(', ')}
                  onChange={e => updateConfig(key, e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  className="w-full px-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
                  style={{ color: 'var(--text-primary)' }}
                />
              </div>
            ))}
          </div>
        </section>

        {/* Emergency Keywords */}
        <section className="glass-card gradient-border p-5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-tertiary)' }}>Custom Emergency Keywords</h2>
          <input
            type="text"
            value={(config.emergency_keywords || []).join(', ')}
            onChange={e => updateConfig('emergency_keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
            className="w-full px-4 py-2.5 rounded-xl text-[13px] outline-none glass-input"
            style={{ color: 'var(--text-primary)' }}
            placeholder="gas leak, no heat, flooding..."
          />
          <p className="text-[10px] mt-2" style={{ color: 'var(--text-tertiary)' }}>
            Default keywords (always active): gas leak, carbon monoxide, fire, flooding, burst pipe, no heat, no ac, sewage, exposed wires
          </p>
        </section>
      </div>
    </div>
  );
}
