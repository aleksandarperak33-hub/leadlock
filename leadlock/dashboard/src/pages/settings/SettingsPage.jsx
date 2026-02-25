import { useState, useEffect, useRef } from 'react';
import { api } from '../../api/client';
import { Save, Check, AlertCircle } from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import { SectionDivider } from './SectionHeader';
import BusinessInfoSection from './BusinessInfoSection';
import PhoneProvisioningSection from './PhoneProvisioningSection';
import RegistrationStatusSection from './RegistrationStatusSection';
import CRMConnectionSection from './CRMConnectionSection';
import PersonaSection from './PersonaSection';
import BusinessHoursSection from './BusinessHoursSection';
import ServicesSection from './ServicesSection';
import EmergencyKeywordsSection from './EmergencyKeywordsSection';
import BusinessMetricsSection from './BusinessMetricsSection';

export default function SettingsPage() {
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
        <PhoneProvisioningSection
          settings={settings}
          onProvisioned={(phone, data) => setSettings(s => ({
            ...s,
            twilio_phone: phone,
            ten_dlc_status: data?.ten_dlc_status || 'collecting_info',
            twilio_messaging_service_sid: data?.messaging_service_sid,
          }))}
        />
        {settings?.twilio_phone && (
          <>
            <SectionDivider />
            <RegistrationStatusSection settings={settings} setSettings={setSettings} />
          </>
        )}
        <SectionDivider />
        <CRMConnectionSection settings={settings} />
        <SectionDivider />
        <BusinessMetricsSection config={config} updateConfig={updateConfig} />
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
