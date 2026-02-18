import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import { Save, Check, AlertCircle, Phone, Plug, Search, Loader2, Shield, Clock, CheckCircle2, XCircle, Building2 } from 'lucide-react';
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

const CRM_OPTIONS = [
  { value: 'servicetitan', label: 'ServiceTitan' },
  { value: 'housecallpro', label: 'Housecall Pro' },
  { value: 'jobber', label: 'Jobber' },
  { value: 'gohighlevel', label: 'GoHighLevel' },
  { value: 'google_sheets', label: 'Google Sheets' },
];

const BUSINESS_TYPE_OPTIONS = [
  { value: 'sole_proprietorship', label: 'Sole Proprietorship' },
  { value: 'llc', label: 'LLC' },
  { value: 'corporation', label: 'Corporation' },
  { value: 'partnership', label: 'Partnership' },
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
    { label: 'Registration', value: getDisplayStatus(settings?.ten_dlc_status), capitalize: true },
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

function getDisplayStatus(status) {
  const map = {
    pending: 'Not Started',
    collecting_info: 'Info Needed',
    profile_pending: 'In Review',
    profile_approved: 'In Review',
    profile_rejected: 'Action Required',
    brand_pending: 'In Review',
    brand_approved: 'Almost Ready',
    brand_rejected: 'Action Required',
    campaign_pending: 'Almost Ready',
    campaign_rejected: 'Action Required',
    tf_verification_pending: 'In Review',
    tf_rejected: 'Action Required',
    active: 'Active',
  };
  return map[status] || status || 'Not Started';
}

function RegistrationStatusSection({ settings, setSettings }) {
  const status = settings?.ten_dlc_status || 'pending';
  const isActive = status === 'active';
  const isRejected = status.endsWith('_rejected');
  const needsInfo = status === 'collecting_info' && !settings?.business_type;

  return (
    <div>
      <SectionHeader
        title="SMS Registration"
        description="Your number must be registered before it can send outbound SMS."
      />

      {/* Status banner */}
      <RegistrationStatusBanner status={status} />

      {/* Business info form for 10DLC (only show if collecting_info and local number) */}
      {needsInfo && (
        <BusinessRegistrationForm settings={settings} setSettings={setSettings} />
      )}
    </div>
  );
}

function RegistrationStatusBanner({ status }) {
  if (status === 'active') {
    return (
      <div className="flex items-center gap-3 p-4 rounded-xl bg-green-50 border border-green-200/60">
        <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-green-800">Registration Active</p>
          <p className="text-xs text-green-600">Your number is fully registered and can send SMS.</p>
        </div>
      </div>
    );
  }

  if (status.endsWith('_rejected')) {
    return (
      <div className="flex items-center gap-3 p-4 rounded-xl bg-red-50 border border-red-200/60">
        <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-red-800">Registration Rejected</p>
          <p className="text-xs text-red-600">
            Your registration was rejected. Please contact support for assistance.
          </p>
        </div>
      </div>
    );
  }

  if (status === 'collecting_info') {
    return (
      <div className="flex items-center gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200/60 mb-6">
        <Building2 className="w-5 h-5 text-amber-600 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-amber-800">Business Info Required</p>
          <p className="text-xs text-amber-600">
            Submit your business details below to register your number for SMS.
          </p>
        </div>
      </div>
    );
  }

  // Pending states
  const progressSteps = [
    { key: 'profile', label: 'Profile' },
    { key: 'brand', label: 'Brand' },
    { key: 'campaign', label: 'Campaign' },
  ];

  const isTollFree = status.startsWith('tf_');

  const getStepState = (stepKey) => {
    const stateOrder = {
      profile: ['profile_pending', 'profile_approved'],
      brand: ['brand_pending', 'brand_approved'],
      campaign: ['campaign_pending'],
    };

    const completedAfter = {
      profile: ['brand_pending', 'brand_approved', 'campaign_pending', 'active'],
      brand: ['campaign_pending', 'active'],
      campaign: ['active'],
    };

    if (completedAfter[stepKey]?.includes(status)) return 'completed';
    if (stateOrder[stepKey]?.includes(status)) return 'current';
    return 'pending';
  };

  return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-blue-50 border border-blue-200/60">
      <Clock className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
      <div className="flex-1">
        <p className="text-sm font-medium text-blue-800">Registration In Progress</p>
        <p className="text-xs text-blue-600 mb-3">
          {isTollFree
            ? 'Your toll-free number is being verified. This typically takes 1-3 business days.'
            : 'Your number is being registered with carriers. This typically takes 1-5 business days.'}
        </p>

        {!isTollFree && (
          <div className="flex items-center gap-2">
            {progressSteps.map((step, i) => {
              const state = getStepState(step.key);
              return (
                <div key={step.key} className="flex items-center gap-2">
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                    state === 'completed' ? 'bg-green-100 text-green-700' :
                    state === 'current' ? 'bg-blue-100 text-blue-700' :
                    'bg-gray-100 text-gray-400'
                  }`}>
                    {state === 'completed' && <CheckCircle2 className="w-3 h-3" />}
                    {state === 'current' && <Loader2 className="w-3 h-3 animate-spin" />}
                    {step.label}
                  </div>
                  {i < progressSteps.length - 1 && (
                    <div className={`w-4 h-px ${
                      state === 'completed' ? 'bg-green-300' : 'bg-gray-200'
                    }`} />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function BusinessRegistrationForm({ settings, setSettings }) {
  const [businessType, setBusinessType] = useState(settings?.business_type || '');
  const [businessEin, setBusinessEin] = useState(settings?.business_ein || '');
  const [businessWebsite, setBusinessWebsite] = useState(settings?.business_website || '');
  const [street, setStreet] = useState(settings?.business_address?.street || '');
  const [city, setCity] = useState(settings?.business_address?.city || '');
  const [state, setState] = useState(settings?.business_address?.state || '');
  const [zip, setZip] = useState(settings?.business_address?.zip || '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async () => {
    if (!businessType) {
      setError('Business type is required');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const token = localStorage.getItem('ll_token');
      const res = await fetch('/api/v1/settings/business-registration', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          business_type: businessType,
          business_ein: businessEin,
          business_website: businessWebsite,
          business_address: { street, city, state, zip },
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Registration failed');

      setSuccess(true);
      setSettings(s => ({
        ...s,
        ten_dlc_status: data.status,
        business_type: businessType,
        business_ein: businessEin,
        business_website: businessWebsite,
        business_address: { street, city, state, zip },
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="flex items-center gap-3 p-4 rounded-xl bg-green-50 border border-green-200/60">
        <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-green-800">Registration Submitted</p>
          <p className="text-xs text-green-600">
            Your business info has been submitted for review. This typically takes 1-3 business days.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <label className={LABEL_CLASSES}>Business Type *</label>
        <select
          value={businessType}
          onChange={(e) => setBusinessType(e.target.value)}
          className={`${INPUT_CLASSES} cursor-pointer`}
        >
          <option value="">Select business type...</option>
          {BUSINESS_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className={LABEL_CLASSES}>
          EIN / Tax ID {businessType === 'sole_proprietorship' ? '(optional)' : ''}
        </label>
        <input
          type="text"
          value={businessEin}
          onChange={(e) => setBusinessEin(e.target.value.replace(/[^\d-]/g, '').slice(0, 11))}
          className={INPUT_CLASSES}
          placeholder="XX-XXXXXXX"
        />
      </div>

      <div>
        <label className={LABEL_CLASSES}>Business Website</label>
        <input
          type="url"
          value={businessWebsite}
          onChange={(e) => setBusinessWebsite(e.target.value)}
          className={INPUT_CLASSES}
          placeholder="https://yourcompany.com"
        />
      </div>

      <div>
        <label className={LABEL_CLASSES}>Business Address</label>
        <div className="space-y-3">
          <input
            type="text"
            value={street}
            onChange={(e) => setStreet(e.target.value)}
            className={INPUT_CLASSES}
            placeholder="Street address"
          />
          <div className="grid grid-cols-3 gap-3">
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className={INPUT_CLASSES}
              placeholder="City"
            />
            <input
              type="text"
              value={state}
              onChange={(e) => setState(e.target.value.toUpperCase().slice(0, 2))}
              className={INPUT_CLASSES}
              placeholder="State"
            />
            <input
              type="text"
              value={zip}
              onChange={(e) => setZip(e.target.value.replace(/\D/g, '').slice(0, 5))}
              className={INPUT_CLASSES}
              placeholder="ZIP"
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="px-4 py-2 rounded-lg bg-red-50 border border-red-200/60 text-red-600 text-sm">
          {error}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={submitting || !businessType}
        className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
        {submitting ? 'Submitting...' : 'Submit Registration'}
      </button>
    </div>
  );
}

function PhoneProvisioningSection({ settings, onProvisioned }) {
  const [areaCode, setAreaCode] = useState('');
  const [numbers, setNumbers] = useState([]);
  const [searching, setSearching] = useState(false);
  const [provisioning, setProvisioning] = useState('');
  const [error, setError] = useState('');

  if (settings?.twilio_phone) {
    return (
      <div>
        <SectionHeader title="Phone Number" description="Your dedicated SMS line." />
        <div className="bg-green-50 border border-green-200/60 rounded-xl p-4 flex items-center gap-3">
          <Phone className="w-5 h-5 text-green-600" />
          <div>
            <p className="text-sm font-medium text-green-800">{settings.twilio_phone}</p>
            <p className="text-xs text-green-600">Active and receiving leads</p>
          </div>
        </div>
      </div>
    );
  }

  const handleSearch = async () => {
    if (!areaCode || areaCode.length !== 3) return;
    setSearching(true);
    setError('');
    setNumbers([]);
    try {
      const token = localStorage.getItem('ll_token');
      const res = await fetch(`/api/v1/settings/available-numbers?area_code=${areaCode}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Search failed');
      setNumbers(data.numbers || []);
      if (!data.numbers?.length) setError('No numbers available for this area code');
    } catch (e) {
      setError(e.message);
    } finally {
      setSearching(false);
    }
  };

  const handleProvision = async (phoneNumber) => {
    setProvisioning(phoneNumber);
    setError('');
    try {
      const token = localStorage.getItem('ll_token');
      const res = await fetch('/api/v1/settings/provision-number', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ phone_number: phoneNumber }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Provisioning failed');
      onProvisioned(data.phone_number, data);
    } catch (e) {
      setError(e.message);
    } finally {
      setProvisioning('');
    }
  };

  return (
    <div>
      <SectionHeader title="Phone Number" description="Get a dedicated SMS line for your business." />
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          value={areaCode}
          onChange={(e) => setAreaCode(e.target.value.replace(/\D/g, '').slice(0, 3))}
          placeholder="Area code (e.g. 512)"
          className={`${INPUT_CLASSES} max-w-[160px]`}
        />
        <button
          onClick={handleSearch}
          disabled={searching || areaCode.length !== 3}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer"
        >
          {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          Search
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-red-50 border border-red-200/60 text-red-600 text-sm">
          {error}
        </div>
      )}

      {numbers.length > 0 && (
        <div className="space-y-2">
          {numbers.map((num) => (
            <div key={num.phone_number} className="flex items-center justify-between p-3 bg-gray-50 border border-gray-200/60 rounded-xl">
              <div>
                <p className="text-sm font-medium text-gray-900">{num.friendly_name}</p>
                <p className="text-xs text-gray-400">{num.locality}, {num.region}</p>
              </div>
              <button
                onClick={() => handleProvision(num.phone_number)}
                disabled={!!provisioning}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer"
              >
                {provisioning === num.phone_number ? 'Provisioning...' : 'Select'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CRMConnectionSection({ settings }) {
  const [crmType, setCrmType] = useState(settings?.crm_type || 'google_sheets');
  const [apiKey, setApiKey] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const token = localStorage.getItem('ll_token');
      const res = await fetch('/api/v1/integrations/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ crm_type: crmType, api_key: apiKey, tenant_id: tenantId }),
      });
      const data = await res.json();
      setTestResult(data);
    } catch (e) {
      setTestResult({ connected: false, message: e.message });
    } finally {
      setTesting(false);
    }
  };

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const token = localStorage.getItem('ll_token');
      const res = await fetch('/api/v1/integrations/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ crm_type: crmType, api_key: apiKey, tenant_id: tenantId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Connection failed');
      setTestResult({ connected: true, message: 'CRM connected successfully!' });
    } catch (e) {
      setTestResult({ connected: false, message: e.message });
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div>
      <SectionHeader title="CRM Integration" description="Connect your CRM for automatic booking sync." />
      <div className="space-y-4">
        <div>
          <label className={LABEL_CLASSES}>CRM Platform</label>
          <select
            value={crmType}
            onChange={(e) => { setCrmType(e.target.value); setTestResult(null); }}
            className={`${INPUT_CLASSES} cursor-pointer`}
          >
            {CRM_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {crmType !== 'google_sheets' && (
          <>
            <div>
              <label className={LABEL_CLASSES}>API Key</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className={INPUT_CLASSES}
                placeholder="Enter your API key"
              />
            </div>
            {crmType === 'gohighlevel' && (
              <div>
                <label className={LABEL_CLASSES}>Location ID</label>
                <input
                  type="text"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  className={INPUT_CLASSES}
                  placeholder="Your GoHighLevel location ID"
                />
              </div>
            )}
            <div className="flex gap-3">
              <button
                onClick={handleTest}
                disabled={testing || !apiKey}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium border border-gray-200 hover:bg-gray-50 text-gray-700 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />}
                Test Connection
              </button>
              <button
                onClick={handleConnect}
                disabled={connecting || !apiKey || !testResult?.connected}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer"
              >
                {connecting ? 'Connecting...' : 'Connect'}
              </button>
            </div>
          </>
        )}

        {testResult && (
          <div className={`px-4 py-3 rounded-xl text-sm ${
            testResult.connected
              ? 'bg-green-50 border border-green-200/60 text-green-700'
              : 'bg-red-50 border border-red-200/60 text-red-600'
          }`}>
            {testResult.message}
            {testResult.technicians_found > 0 && (
              <span className="ml-2 text-xs">({testResult.technicians_found} team members found)</span>
            )}
          </div>
        )}
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
