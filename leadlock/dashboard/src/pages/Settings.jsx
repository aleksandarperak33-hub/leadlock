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
    return <div className="h-96 bg-slate-900 border border-slate-800 rounded-xl animate-pulse" />;
  }

  const persona = config.persona || {};
  const hours = config.hours || {};
  const services = config.services || {};

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors disabled:opacity-50"
        >
          {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {saved ? 'Saved!' : saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="space-y-6">
        {/* Business Info (read-only) */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-4">Business Information</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-slate-500">Business Name</span>
              <p className="text-white mt-1">{settings?.business_name || '\u2014'}</p>
            </div>
            <div>
              <span className="text-slate-500">Trade Type</span>
              <p className="text-white mt-1 capitalize">{settings?.trade_type || '\u2014'}</p>
            </div>
            <div>
              <span className="text-slate-500">Twilio Number</span>
              <p className="text-white mt-1">{settings?.twilio_phone || 'Not assigned'}</p>
            </div>
            <div>
              <span className="text-slate-500">10DLC Status</span>
              <p className="text-white mt-1 capitalize">{settings?.ten_dlc_status || 'pending'}</p>
            </div>
          </div>
        </section>

        {/* AI Persona */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-4">AI Persona</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Rep Name</label>
              <input
                type="text"
                value={persona.rep_name || ''}
                onChange={e => updateConfig('persona.rep_name', e.target.value)}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Tone</label>
              <select
                value={persona.tone || 'friendly_professional'}
                onChange={e => updateConfig('persona.tone', e.target.value)}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              >
                <option value="friendly_professional">Friendly Professional</option>
                <option value="casual">Casual</option>
                <option value="formal">Formal</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Emergency Contact Phone</label>
              <input
                type="text"
                value={persona.emergency_contact_phone || ''}
                onChange={e => updateConfig('persona.emergency_contact_phone', e.target.value)}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
                placeholder="+15551234567"
              />
            </div>
          </div>
        </section>

        {/* Business Hours */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-4">Business Hours</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Weekday Start</label>
              <input
                type="time"
                value={hours.business?.start || '07:00'}
                onChange={e => updateConfig('hours.business.start', e.target.value)}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Weekday End</label>
              <input
                type="time"
                value={hours.business?.end || '18:00'}
                onChange={e => updateConfig('hours.business.end', e.target.value)}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              />
            </div>
          </div>
          <div className="mt-4">
            <label className="block text-xs text-slate-400 mb-1.5">After Hours Handling</label>
            <select
              value={hours.after_hours_handling || 'ai_responds_books_next_available'}
              onChange={e => updateConfig('hours.after_hours_handling', e.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
            >
              <option value="ai_responds_books_next_available">AI responds, books next available</option>
              <option value="ai_responds_owner_notified">AI responds, owner notified</option>
              <option value="do_not_respond">Do not respond until business hours</option>
            </select>
          </div>
        </section>

        {/* Services */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-4">Services</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Primary Services (comma-separated)</label>
              <input
                type="text"
                value={(services.primary || []).join(', ')}
                onChange={e => updateConfig('services.primary', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Secondary Services (comma-separated)</label>
              <input
                type="text"
                value={(services.secondary || []).join(', ')}
                onChange={e => updateConfig('services.secondary', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Do Not Quote (comma-separated)</label>
              <input
                type="text"
                value={(services.do_not_quote || []).join(', ')}
                onChange={e => updateConfig('services.do_not_quote', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              />
            </div>
          </div>
        </section>

        {/* Emergency Keywords */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-4">Custom Emergency Keywords</h2>
          <input
            type="text"
            value={(config.emergency_keywords || []).join(', ')}
            onChange={e => updateConfig('emergency_keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
            placeholder="gas leak, no heat, flooding..."
          />
          <p className="text-[11px] text-slate-500 mt-2">
            Default keywords (always active): gas leak, carbon monoxide, fire, flooding, burst pipe, no heat, no ac, sewage, exposed wires
          </p>
        </section>
      </div>
    </div>
  );
}
