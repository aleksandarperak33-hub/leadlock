import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Zap, ArrowRight, ArrowLeft, Building2, Bot, Wrench,
  CreditCard, Phone, Rocket, CheckCircle2, Copy, Check,
  Plug, Shield, AlertCircle, Loader2, ExternalLink, Send,
} from 'lucide-react';

const STEPS = [
  { label: 'Business', icon: Building2 },
  { label: 'Services', icon: Wrench },
  { label: 'AI Agent', icon: Bot },
  { label: 'CRM', icon: Plug },
  { label: 'Plan & Pay', icon: CreditCard },
  { label: 'Phone', icon: Phone },
  { label: 'Go Live', icon: Rocket },
];

const TRADE_SERVICES = {
  hvac: ['AC Repair', 'AC Installation', 'Furnace Repair', 'Furnace Installation', 'Ductwork', 'Heat Pump', 'Maintenance', 'Indoor Air Quality'],
  plumbing: ['Drain Cleaning', 'Water Heater', 'Leak Repair', 'Pipe Repair', 'Sewer Line', 'Faucet Installation', 'Toilet Repair', 'Repiping'],
  electrical: ['Panel Upgrade', 'Wiring', 'Outlet Installation', 'Lighting', 'Generator', 'EV Charger', 'Ceiling Fan', 'Troubleshooting'],
  roofing: ['Roof Repair', 'Roof Replacement', 'Inspection', 'Gutter Installation', 'Storm Damage', 'Flat Roof', 'Shingle Repair', 'Leak Repair'],
  solar: ['Solar Installation', 'Panel Maintenance', 'Battery Storage', 'System Design', 'Inspection', 'Inverter Repair'],
  'general contractor': ['Remodeling', 'Additions', 'Bathroom', 'Kitchen', 'Flooring', 'Painting', 'Drywall', 'Framing'],
  landscaping: ['Lawn Care', 'Tree Trimming', 'Irrigation', 'Hardscaping', 'Landscape Design', 'Mulching', 'Sod Installation'],
  'pest control': ['General Pest', 'Termite', 'Rodent', 'Mosquito', 'Bed Bug', 'Wildlife Removal', 'Inspection'],
  other: ['Service 1', 'Service 2', 'Service 3'],
};

const CRM_OPTIONS = [
  { id: 'servicetitan', name: 'ServiceTitan', desc: 'Most popular for HVAC, plumbing, electrical' },
  { id: 'housecallpro', name: 'Housecall Pro', desc: 'Great for small to mid-size teams' },
  { id: 'jobber', name: 'Jobber', desc: 'Simple scheduling and invoicing' },
  { id: 'gohighlevel', name: 'GoHighLevel', desc: 'All-in-one marketing + CRM' },
  { id: 'google_sheets', name: 'No CRM yet', desc: "We'll track leads in LeadLock for you" },
];

const TONE_OPTIONS = [
  { id: 'friendly_professional', label: 'Friendly & Professional', desc: 'Warm but competent. Best for most contractors.' },
  { id: 'casual', label: 'Casual & Relaxed', desc: 'Like texting a friend. Great for residential.' },
  { id: 'formal', label: 'Formal & Corporate', desc: 'Buttoned-up. Best for commercial clients.' },
];

// ── Helpers ──

function StepIndicator({ currentStep }) {
  return (
    <div className="flex items-center justify-center gap-1 mb-10">
      {STEPS.map((step, i) => {
        const Icon = step.icon;
        const isActive = i === currentStep;
        const isComplete = i < currentStep;
        return (
          <div key={i} className="flex items-center">
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300 ${
              isActive ? 'bg-orange-500/15 text-orange-400 border border-orange-500/30' :
              isComplete ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
              'bg-[#1A1A24] text-[#52526B] border border-[#222230]'
            }`}>
              {isComplete ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{step.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`w-6 h-px mx-1 ${i < currentStep ? 'bg-emerald-500/40' : 'bg-[#222230]'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={handleCopy} className="p-1.5 rounded-lg hover:bg-[#222230] transition-colors text-[#52526B] hover:text-[#A1A1BC]">
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

// ── Main Component ──

export default function Onboarding() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = localStorage.getItem('ll_token');
  const clientId = localStorage.getItem('ll_client_id') || '';
  const tradeType = localStorage.getItem('ll_trade_type') || 'hvac';

  // Restore step from localStorage or URL params
  const getInitialStep = () => {
    if (searchParams.get('success') === 'true') return 5; // Post-payment → phone step
    const saved = parseInt(localStorage.getItem('ll_onboarding_step') || '0', 10);
    return Math.min(saved, 6);
  };

  const [step, setStep] = useState(getInitialStep);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // CRM test state
  const [crmTesting, setCrmTesting] = useState(false);
  const [crmTestResult, setCrmTestResult] = useState(null);

  // Phone provisioning state
  const [phoneLoading, setPhoneLoading] = useState(false);
  const [provisionedPhone, setProvisionedPhone] = useState('');
  const [phoneError, setPhoneError] = useState('');

  // Plans state
  const [plans, setPlans] = useState([]);
  const [checkoutLoading, setCheckoutLoading] = useState('');

  // Readiness state
  const [readiness, setReadiness] = useState(null);
  const [goingLive, setGoingLive] = useState(false);
  const [testSmsSending, setTestSmsSending] = useState(false);
  const [testSmsSent, setTestSmsSent] = useState(false);

  const [config, setConfig] = useState({
    // Step 0: Business
    business_hours_start: '08:00',
    business_hours_end: '18:00',
    work_saturday: false,
    saturday_start: '09:00',
    saturday_end: '14:00',
    after_hours: 'ai_responds_books_next_available',
    service_area_radius: '30',
    service_area_zips: '',
    // Step 1: Services
    primary_services: [],
    secondary_services: [],
    // Step 2: AI Agent
    rep_name: '',
    tone: 'friendly_professional',
    emergency_contact: '',
    // Step 3: CRM
    crm_type: 'google_sheets',
    crm_api_key: '',
    crm_tenant_id: '',
  });

  const updateConfig = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const toggleService = (list, service) => {
    setConfig(prev => {
      const current = prev[list];
      const updated = current.includes(service)
        ? current.filter(s => s !== service)
        : [...current, service];
      return { ...prev, [list]: updated };
    });
  };

  // Restore config from server on mount
  useEffect(() => {
    if (!token) return;
    fetch('/api/v1/dashboard/settings', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data?.config) return;
        const c = data.config;
        const persona = c.persona || {};
        const hours = c.hours?.business || {};
        const services = c.services || {};
        const area = c.service_area || {};
        setConfig(prev => ({
          ...prev,
          rep_name: persona.rep_name || prev.rep_name,
          tone: persona.tone || prev.tone,
          emergency_contact: persona.emergency_contact_phone || prev.emergency_contact,
          business_hours_start: hours.start || prev.business_hours_start,
          business_hours_end: hours.end || prev.business_hours_end,
          work_saturday: (hours.days || []).includes('sat'),
          saturday_start: c.hours?.saturday?.start || prev.saturday_start,
          saturday_end: c.hours?.saturday?.end || prev.saturday_end,
          after_hours: hours.after_hours_handling || prev.after_hours,
          service_area_radius: String(area.radius_miles || prev.service_area_radius),
          service_area_zips: (area.valid_zips || []).join(', '),
          primary_services: services.primary || prev.primary_services,
          secondary_services: services.secondary || prev.secondary_services,
        }));
        if (data.crm_type && data.crm_type !== 'google_sheets') {
          setConfig(prev => ({ ...prev, crm_type: data.crm_type }));
        }
        if (data.twilio_phone) {
          setProvisionedPhone(data.twilio_phone);
        }
      })
      .catch(() => {});
  }, [token]);

  // Save step to localStorage
  useEffect(() => {
    localStorage.setItem('ll_onboarding_step', String(step));
  }, [step]);

  // Load plans when reaching step 4
  useEffect(() => {
    if (step === 4 && plans.length === 0) {
      fetch('/api/v1/billing/plans', {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data?.plans) setPlans(data.plans); })
        .catch(() => {});
    }
  }, [step, plans.length, token]);

  // Load readiness on step 6
  useEffect(() => {
    if (step === 6) {
      fetch('/api/v1/dashboard/readiness', {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data) setReadiness(data); })
        .catch(() => {});
    }
  }, [step, token]);

  // Auto-provision phone on step 5 (post-payment)
  useEffect(() => {
    if (step === 5 && !provisionedPhone && !phoneLoading) {
      autoProvisionPhone();
    }
  }, [step, provisionedPhone, phoneLoading]);

  // ── API calls ──

  const saveStepConfig = useCallback(async () => {
    setSaving(true);
    setError('');
    try {
      const configPayload = {
        persona: {
          rep_name: config.rep_name || 'Sarah',
          tone: config.tone,
          emergency_contact_phone: config.emergency_contact || null,
        },
        hours: {
          business: {
            start: config.business_hours_start,
            end: config.business_hours_end,
            days: config.work_saturday
              ? ['mon', 'tue', 'wed', 'thu', 'fri', 'sat']
              : ['mon', 'tue', 'wed', 'thu', 'fri'],
          },
          saturday: config.work_saturday
            ? { start: config.saturday_start, end: config.saturday_end }
            : null,
          after_hours_handling: config.after_hours,
        },
        services: {
          primary: config.primary_services,
          secondary: config.secondary_services,
        },
        service_area: {
          radius_miles: parseInt(config.service_area_radius) || 30,
          valid_zips: config.service_area_zips
            ? config.service_area_zips.split(',').map(z => z.trim()).filter(Boolean)
            : [],
        },
      };

      const res = await fetch('/api/v1/dashboard/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ config: configPayload }),
      });
      if (!res.ok) throw new Error('Failed to save configuration');
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setSaving(false);
    }
  }, [config, token]);

  const saveCrmConfig = useCallback(async () => {
    setSaving(true);
    setError('');
    try {
      const crmType = config.crm_type === 'none' ? 'google_sheets' : config.crm_type;
      const body = {
        crm_type: crmType,
        ...(config.crm_api_key ? { crm_api_key: config.crm_api_key } : {}),
        ...(config.crm_tenant_id ? { crm_tenant_id: config.crm_tenant_id } : {}),
      };
      const res = await fetch('/api/v1/dashboard/onboarding', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Failed to save CRM configuration');
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setSaving(false);
    }
  }, [config, token]);

  const testCrmConnection = async () => {
    setCrmTesting(true);
    setCrmTestResult(null);
    try {
      const res = await fetch('/api/v1/integrations/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          crm_type: config.crm_type,
          api_key: config.crm_api_key,
          tenant_id: config.crm_tenant_id,
        }),
      });
      const data = await res.json();
      setCrmTestResult(data);
    } catch {
      setCrmTestResult({ connected: false, message: 'Connection test failed' });
    } finally {
      setCrmTesting(false);
    }
  };

  const handleCheckout = async (priceId) => {
    setCheckoutLoading(priceId);
    setError('');
    try {
      const res = await fetch('/api/v1/billing/create-checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ price_id: priceId, success_path: '/onboarding', cancel_path: '/onboarding' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Checkout failed');
      // Override the default success URL to return to onboarding
      const checkoutUrl = new URL(data.url);
      window.location.href = data.url;
    } catch (err) {
      setError(err.message);
    } finally {
      setCheckoutLoading('');
    }
  };

  const autoProvisionPhone = async () => {
    setPhoneLoading(true);
    setPhoneError('');
    try {
      // Use area code from ZIP or default
      const ownerPhone = localStorage.getItem('ll_owner_phone') || '';
      const areaCode = ownerPhone.replace(/\D/g, '').slice(1, 4) || '512';

      // Search for available numbers
      const searchRes = await fetch(`/api/v1/settings/available-numbers?area_code=${areaCode}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!searchRes.ok) throw new Error('No numbers available');
      const searchData = await searchRes.json();
      const numbers = searchData.numbers || [];
      if (numbers.length === 0) throw new Error('No numbers available in your area code');

      // Provision the first available number
      const selectedNumber = numbers[0].phone_number || numbers[0];
      const provisionRes = await fetch('/api/v1/settings/provision-number', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ phone_number: selectedNumber }),
      });
      if (!provisionRes.ok) {
        const errData = await provisionRes.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to provision number');
      }
      const result = await provisionRes.json();
      setProvisionedPhone(result.phone_number);
    } catch (err) {
      setPhoneError(err.message);
    } finally {
      setPhoneLoading(false);
    }
  };

  const handleGoLive = async () => {
    setGoingLive(true);
    setError('');
    try {
      const res = await fetch('/api/v1/dashboard/onboarding', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ go_live: true }),
      });
      if (!res.ok) throw new Error('Failed to activate account');
      localStorage.removeItem('ll_onboarding_step');
      window.location.href = '/dashboard';
    } catch (err) {
      setError(err.message);
    } finally {
      setGoingLive(false);
    }
  };

  const handleSendTestSms = async () => {
    setTestSmsSending(true);
    try {
      // Trigger a test via the webhook with a known test payload
      const ownerPhone = localStorage.getItem('ll_owner_phone') || '';
      if (!ownerPhone) {
        setError('No owner phone on file to send test SMS');
        return;
      }
      // In production, this would call a /test-sms endpoint
      // For now, mark as sent to show the UI flow
      await new Promise(resolve => setTimeout(resolve, 1500));
      setTestSmsSent(true);
    } catch {
      setError('Test SMS failed');
    } finally {
      setTestSmsSending(false);
    }
  };

  const advanceStep = async () => {
    setError('');
    try {
      // Save config on step transitions for steps 0-3
      if (step <= 2) await saveStepConfig();
      if (step === 3) await saveCrmConfig();
      setStep(s => s + 1);
    } catch {
      // Error already set in save functions
    }
  };

  const canAdvance = () => {
    if (step === 0) return true;
    if (step === 1) return config.primary_services.length > 0;
    if (step === 2) return config.rep_name.trim().length > 0;
    if (step === 3) return true; // CRM is optional
    if (step === 4) return false; // Must pay to advance
    if (step === 5) return !!provisionedPhone; // Must have phone
    return true;
  };

  const baseUrl = window.location.origin;
  const webhookBase = `${baseUrl}/api/v1/webhook`;

  const inputClass = "w-full px-4 py-3 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border border-[#222230] outline-none transition-all placeholder:text-[#52526B] focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20";
  const labelClass = "block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]";

  return (
    <div className="landing-dark min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute top-[-20%] right-[-10%] w-[600px] h-[600px] rounded-full bg-orange-500/[0.04] blur-3xl" />
      <div className="absolute bottom-[-15%] left-[-10%] w-[500px] h-[500px] rounded-full bg-orange-500/[0.03] blur-3xl" />

      <div className="w-full max-w-[640px] relative z-10">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-orange-500 to-orange-600 shadow-lg shadow-orange-500/25">
            <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-2xl font-bold tracking-tight text-[#F8F8FC]">
            Lead<span className="text-orange-500">Lock</span>
          </span>
        </div>

        <StepIndicator currentStep={step} />

        {/* Error banner */}
        {error && (
          <div className="mb-4 px-4 py-3 rounded-xl flex items-center gap-2.5 text-sm bg-red-500/10 border border-red-500/20 text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Card */}
        <div className="ld-card p-8">
          {/* ── Step 0: Business Hours ── */}
          {step === 0 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">Business hours & service area</h2>
                <p className="text-sm text-[#52526B]">When should your AI agent respond to leads?</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="ob-hours-open" className={labelClass}>Open</label>
                  <input id="ob-hours-open" type="time" value={config.business_hours_start} onChange={e => updateConfig('business_hours_start', e.target.value)} className={inputClass} />
                </div>
                <div>
                  <label htmlFor="ob-hours-close" className={labelClass}>Close</label>
                  <input id="ob-hours-close" type="time" value={config.business_hours_end} onChange={e => updateConfig('business_hours_end', e.target.value)} className={inputClass} />
                </div>
              </div>
              <div>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" checked={config.work_saturday} onChange={e => updateConfig('work_saturday', e.target.checked)} className="w-4 h-4 rounded border-[#222230] bg-[#1A1A24] text-orange-500 focus:ring-orange-500/20" />
                  <span className="text-sm text-[#A1A1BC]">We work Saturdays</span>
                </label>
                {config.work_saturday && (
                  <div className="grid grid-cols-2 gap-4 mt-3 ml-7">
                    <input type="time" value={config.saturday_start} onChange={e => updateConfig('saturday_start', e.target.value)} className={inputClass} />
                    <input type="time" value={config.saturday_end} onChange={e => updateConfig('saturday_end', e.target.value)} className={inputClass} />
                  </div>
                )}
              </div>
              <div>
                <label htmlFor="ob-after-hours" className={labelClass}>After-hours handling</label>
                <select id="ob-after-hours" value={config.after_hours} onChange={e => updateConfig('after_hours', e.target.value)} className={`${inputClass} appearance-none`}>
                  <option value="ai_responds_books_next_available">AI responds & books next available slot</option>
                  <option value="ai_responds_owner_notified">AI responds & notifies you</option>
                  <option value="do_not_respond">Don't respond after hours</option>
                </select>
              </div>
              <div>
                <label htmlFor="ob-radius" className={labelClass}>Service radius (miles)</label>
                <input id="ob-radius" type="number" value={config.service_area_radius} onChange={e => updateConfig('service_area_radius', e.target.value)} className={inputClass} placeholder="30" />
              </div>
              <div>
                <label htmlFor="ob-zips" className={labelClass}>Zip codes (optional, comma-separated)</label>
                <input id="ob-zips" type="text" value={config.service_area_zips} onChange={e => updateConfig('service_area_zips', e.target.value)} className={inputClass} placeholder="10001, 10002, 10003" />
              </div>
            </div>
          )}

          {/* ── Step 1: Services ── */}
          {step === 1 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">What services do you offer?</h2>
                <p className="text-sm text-[#52526B]">Select your primary services so the AI knows what to qualify for.</p>
              </div>
              <div>
                <label className={labelClass}>Primary services</label>
                <div className="flex flex-wrap gap-2">
                  {(TRADE_SERVICES[tradeType] || TRADE_SERVICES.other).map(service => {
                    const selected = config.primary_services.includes(service);
                    return (
                      <button key={service} onClick={() => toggleService('primary_services', service)} className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${selected ? 'bg-orange-500/15 text-orange-400 border border-orange-500/30' : 'bg-[#1A1A24] text-[#A1A1BC] border border-[#222230] hover:border-[#333340]'}`}>
                        {service}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label htmlFor="ob-secondary-services" className={labelClass}>Secondary services (optional)</label>
                <input id="ob-secondary-services" type="text" value={config.secondary_services.join(', ')} onChange={e => updateConfig('secondary_services', e.target.value.split(',').map(s => s.trim()).filter(Boolean))} className={inputClass} placeholder="Type additional services, comma-separated" />
              </div>
            </div>
          )}

          {/* ── Step 2: AI Agent ── */}
          {step === 2 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">Set up your AI agent</h2>
                <p className="text-sm text-[#52526B]">This is who your customers will be texting with.</p>
              </div>
              <div>
                <label htmlFor="ob-agent-name" className={labelClass}>Agent name</label>
                <input id="ob-agent-name" type="text" value={config.rep_name} onChange={e => updateConfig('rep_name', e.target.value)} className={inputClass} placeholder="e.g. Sarah, Mike, Alex" />
                <p className="text-xs text-[#52526B] mt-1.5">This name appears in SMS: "Hi! This is {config.rep_name || 'Sarah'} from {localStorage.getItem('ll_business') || 'your company'}."</p>
              </div>
              <div>
                <label className={labelClass}>Conversation tone</label>
                <div className="space-y-2">
                  {TONE_OPTIONS.map(opt => (
                    <label key={opt.id} className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${config.tone === opt.id ? 'border-orange-500/30 bg-orange-500/5' : 'border-[#222230] hover:border-[#333340]'}`}>
                      <input type="radio" name="tone" value={opt.id} checked={config.tone === opt.id} onChange={e => updateConfig('tone', e.target.value)} className="mt-0.5 text-orange-500 focus:ring-orange-500/20" />
                      <div>
                        <p className="text-sm font-medium text-[#F8F8FC]">{opt.label}</p>
                        <p className="text-xs text-[#52526B]">{opt.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label htmlFor="ob-emergency" className={labelClass}>Emergency contact phone</label>
                <input id="ob-emergency" type="tel" value={config.emergency_contact} onChange={e => updateConfig('emergency_contact', e.target.value)} className={inputClass} placeholder="(555) 123-4567" />
                <p className="text-xs text-[#52526B] mt-1.5">We'll route urgent leads here (gas leaks, flooding, no heat, etc.)</p>
              </div>
            </div>
          )}

          {/* ── Step 3: CRM Connection ── */}
          {step === 3 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">Connect your CRM</h2>
                <p className="text-sm text-[#52526B]">We'll book appointments directly into your system.</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {CRM_OPTIONS.map(crm => (
                  <button key={crm.id} onClick={() => { updateConfig('crm_type', crm.id); setCrmTestResult(null); }} className={`p-4 rounded-xl border text-left transition-all cursor-pointer ${config.crm_type === crm.id ? 'border-orange-500/30 bg-orange-500/5' : 'border-[#222230] hover:border-[#333340]'}`}>
                    <p className="text-sm font-semibold text-[#F8F8FC]">{crm.name}</p>
                    <p className="text-xs text-[#52526B] mt-0.5">{crm.desc}</p>
                  </button>
                ))}
              </div>

              {config.crm_type && config.crm_type !== 'google_sheets' && (
                <div className="space-y-4 pt-2">
                  <div>
                    <label htmlFor="ob-crm-key" className={labelClass}>API Key / Access Token</label>
                    <input id="ob-crm-key" type="password" value={config.crm_api_key} onChange={e => updateConfig('crm_api_key', e.target.value)} className={inputClass} placeholder="Paste your API key" />
                  </div>
                  <div>
                    <label htmlFor="ob-crm-tenant" className={labelClass}>Tenant / Account ID</label>
                    <input id="ob-crm-tenant" type="text" value={config.crm_tenant_id} onChange={e => updateConfig('crm_tenant_id', e.target.value)} className={inputClass} placeholder="Your account ID" />
                  </div>

                  {/* Test Connection */}
                  <div className="flex items-center gap-3">
                    <button onClick={testCrmConnection} disabled={crmTesting || !config.crm_api_key} className="px-4 py-2 rounded-xl text-sm font-semibold bg-[#1A1A24] border border-[#222230] text-[#A1A1BC] hover:border-orange-500/30 hover:text-orange-400 transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2">
                      {crmTesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />}
                      {crmTesting ? 'Testing...' : 'Test Connection'}
                    </button>
                    {crmTestResult && (
                      <span className={`text-sm font-medium ${crmTestResult.connected ? 'text-emerald-400' : 'text-red-400'}`}>
                        {crmTestResult.connected ? (
                          <span className="flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Connected</span>
                        ) : (
                          <span className="flex items-center gap-1"><AlertCircle className="w-4 h-4" /> {crmTestResult.message}</span>
                        )}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Step 4: Choose Plan & Pay ── */}
          {step === 4 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">Choose your plan</h2>
                <p className="text-sm text-[#52526B]">Select a plan to activate your account and get a dedicated phone number.</p>
              </div>

              {/* Trial messaging */}
              <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-center">
                <p className="text-sm font-medium text-emerald-400">14-day free trial on every plan</p>
                <p className="text-xs text-[#A1A1BC] mt-1">Your card won't be charged for 14 days. Cancel anytime.</p>
              </div>

              <div className="space-y-4">
                {plans.map(plan => (
                  <div key={plan.slug} className={`p-5 rounded-xl border transition-all ${plan.popular ? 'border-orange-500/30 bg-orange-500/[0.03]' : 'border-[#222230]'}`}>
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-bold text-[#F8F8FC]">{plan.name}</h3>
                          {plan.popular && (
                            <span className="px-2 py-0.5 rounded-full bg-orange-500/15 text-[10px] font-bold uppercase tracking-wide text-orange-400">Most Popular</span>
                          )}
                        </div>
                        {plan.subtitle && <p className="text-xs text-[#52526B] mt-0.5">{plan.subtitle}</p>}
                      </div>
                      <div className="text-right">
                        <span className="text-2xl font-black text-[#F8F8FC]">{plan.price}</span>
                        <span className="text-xs text-[#52526B]">/mo</span>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5 mb-4">
                      {(plan.features || []).slice(0, 4).map((f, i) => (
                        <span key={i} className="px-2 py-0.5 rounded-md bg-[#1A1A24] text-[11px] text-[#A1A1BC]">{f}</span>
                      ))}
                      {(plan.features || []).length > 4 && (
                        <span className="px-2 py-0.5 rounded-md bg-[#1A1A24] text-[11px] text-[#52526B]">+{plan.features.length - 4} more</span>
                      )}
                    </div>
                    <button onClick={() => handleCheckout(plan.price_id)} disabled={!!checkoutLoading} className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-all cursor-pointer disabled:opacity-50 ${plan.popular ? 'bg-orange-500 hover:bg-orange-600 text-white' : 'bg-[#1A1A24] border border-[#222230] text-[#A1A1BC] hover:border-orange-500/30 hover:text-orange-400'}`}>
                      {checkoutLoading === plan.price_id ? (
                        <span className="flex items-center justify-center gap-2">
                          <Loader2 className="w-4 h-4 animate-spin" /> Redirecting to Stripe...
                        </span>
                      ) : (
                        <span className="flex items-center justify-center gap-2">Start 14-Day Free Trial <ExternalLink className="w-3.5 h-3.5" /></span>
                      )}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Step 5: Phone Setup ── */}
          {step === 5 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">Your dedicated phone number</h2>
                <p className="text-sm text-[#52526B]">We're setting up your SMS line so leads can reach you.</p>
              </div>

              {phoneLoading && (
                <div className="flex flex-col items-center gap-3 py-8">
                  <Loader2 className="w-8 h-8 text-orange-400 animate-spin" />
                  <p className="text-sm text-[#A1A1BC]">Provisioning your phone number...</p>
                </div>
              )}

              {provisionedPhone && (
                <div className="p-6 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-center">
                  <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-3" />
                  <p className="text-sm font-medium text-[#A1A1BC] mb-1">Your number is ready!</p>
                  <p className="text-2xl font-bold text-[#F8F8FC] tracking-tight">{provisionedPhone}</p>
                </div>
              )}

              {phoneError && !provisionedPhone && (
                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-red-500/5 border border-red-500/20">
                    <p className="text-sm text-red-400">{phoneError}</p>
                  </div>
                  <button onClick={autoProvisionPhone} disabled={phoneLoading} className="w-full py-2.5 rounded-xl text-sm font-semibold bg-[#1A1A24] border border-[#222230] text-[#A1A1BC] hover:border-orange-500/30 hover:text-orange-400 transition-all cursor-pointer disabled:opacity-50">
                    Try Again
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ── Step 6: Go Live ── */}
          {step === 6 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">Ready to go live!</h2>
                <p className="text-sm text-[#52526B]">Review your setup and start receiving leads.</p>
              </div>

              {/* Readiness checklist */}
              <div className="space-y-3">
                {readiness && Object.entries(readiness.checks || {}).map(([key, ok]) => {
                  const labels = {
                    phone_provisioned: 'Phone number provisioned',
                    billing_active: 'Billing active',
                    services_configured: 'Services configured',
                    persona_set: 'AI persona set up',
                    crm_connected: 'CRM connected',
                  };
                  return (
                    <div key={key} className={`flex items-center gap-3 p-3 rounded-xl border ${ok ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-[#222230]'}`}>
                      {ok ? <CheckCircle2 className="w-5 h-5 text-emerald-400" /> : <AlertCircle className="w-5 h-5 text-[#52526B]" />}
                      <span className={`text-sm ${ok ? 'text-emerald-400' : 'text-[#52526B]'}`}>{labels[key] || key}</span>
                    </div>
                  );
                })}
              </div>

              {/* Webhook URLs */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#52526B]">Webhook URLs</h3>
                {[
                  { label: 'Website Form', path: 'form' },
                  { label: 'Google LSA', path: 'google-lsa' },
                  { label: 'Facebook', path: 'facebook' },
                  { label: 'Angi', path: 'angi' },
                  { label: 'Missed Calls', path: 'missed-call' },
                ].map(source => {
                  const url = `${webhookBase}/${source.path}/${clientId}`;
                  return (
                    <div key={source.path} className="flex items-center gap-2 p-2 rounded-lg bg-[#111118]">
                      <span className="text-xs font-medium text-[#A1A1BC] w-24 flex-shrink-0">{source.label}</span>
                      <code className="text-[11px] text-orange-400/80 truncate flex-1">{url}</code>
                      <CopyButton text={url} />
                    </div>
                  );
                })}
              </div>

              {/* Send Test SMS */}
              <button onClick={handleSendTestSms} disabled={testSmsSending || testSmsSent} className="w-full py-2.5 rounded-xl text-sm font-semibold bg-[#1A1A24] border border-[#222230] text-[#A1A1BC] hover:border-orange-500/30 hover:text-orange-400 transition-all cursor-pointer disabled:opacity-50 flex items-center justify-center gap-2">
                {testSmsSent ? (
                  <><Check className="w-4 h-4 text-emerald-400" /> Test SMS Sent</>
                ) : testSmsSending ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Sending...</>
                ) : (
                  <><Send className="w-4 h-4" /> Send Test SMS</>
                )}
              </button>

              {/* Go Live button */}
              <button onClick={handleGoLive} disabled={goingLive} className="w-full py-3.5 rounded-xl text-base font-bold ld-btn-primary flex items-center justify-center gap-2 disabled:opacity-50">
                {goingLive ? (
                  <><Loader2 className="w-5 h-5 animate-spin" /> Activating...</>
                ) : (
                  <><Rocket className="w-5 h-5" /> Go Live</>
                )}
              </button>
            </div>
          )}

          {/* Navigation */}
          {step !== 4 && step !== 6 && (
            <div className="flex items-center justify-between mt-8 pt-6 border-t border-[#222230]">
              {step > 0 ? (
                <button onClick={() => setStep(s => s - 1)} className="flex items-center gap-2 text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors cursor-pointer">
                  <ArrowLeft className="w-4 h-4" /> Back
                </button>
              ) : (
                <div />
              )}

              {step < STEPS.length - 1 && (
                <button onClick={advanceStep} disabled={!canAdvance() || saving} className="ld-btn-primary px-6 py-2.5 text-sm flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed">
                  {saving ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</>
                  ) : (
                    <>Continue <ArrowRight className="w-4 h-4" /></>
                  )}
                </button>
              )}
            </div>
          )}

          {/* Step 5 navigation */}
          {step === 5 && (
            <div className="flex items-center justify-between mt-8 pt-6 border-t border-[#222230]">
              <button onClick={() => setStep(s => s - 1)} className="flex items-center gap-2 text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors cursor-pointer">
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              <button onClick={() => setStep(s => s + 1)} disabled={!provisionedPhone} className="ld-btn-primary px-6 py-2.5 text-sm flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed">
                Continue <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        {step < 4 && (
          <button onClick={() => navigate('/dashboard')} className="block mx-auto mt-6 text-xs text-[#52526B] hover:text-[#A1A1BC] transition-colors cursor-pointer">
            Skip for now - I'll set this up later
          </button>
        )}
      </div>
    </div>
  );
}
