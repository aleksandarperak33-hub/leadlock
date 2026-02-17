import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Zap, ArrowRight, ArrowLeft, Building2, Bot, Wrench,
  Clock, Globe, CheckCircle2, Copy, Check, Plug, ExternalLink,
} from 'lucide-react';

const STEPS = [
  { label: 'Business', icon: Building2 },
  { label: 'Services', icon: Wrench },
  { label: 'AI Agent', icon: Bot },
  { label: 'CRM', icon: Plug },
  { label: 'Lead Sources', icon: Globe },
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
  { id: 'google_sheets', name: 'Google Sheets', desc: 'Free fallback — no integration needed' },
  { id: 'none', name: 'No CRM yet', desc: "We'll use Google Sheets until you're ready" },
];

const TONE_OPTIONS = [
  { id: 'friendly_professional', label: 'Friendly & Professional', desc: 'Warm but competent. Best for most contractors.' },
  { id: 'casual', label: 'Casual & Relaxed', desc: 'Like texting a friend. Great for residential.' },
  { id: 'formal', label: 'Formal & Corporate', desc: 'Buttoned-up. Best for commercial clients.' },
];

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
              {isComplete ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : (
                <Icon className="w-3.5 h-3.5" />
              )}
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

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const clientId = localStorage.getItem('ll_client_id') || '';
  const tradeType = localStorage.getItem('ll_trade_type') || 'hvac';

  const [config, setConfig] = useState({
    // Step 1: Business
    business_hours_start: '08:00',
    business_hours_end: '18:00',
    work_saturday: false,
    saturday_start: '09:00',
    saturday_end: '14:00',
    after_hours: 'ai_responds_books_next_available',
    service_area_radius: '30',
    service_area_zips: '',
    // Step 2: Services
    primary_services: [],
    secondary_services: [],
    // Step 3: AI Agent
    rep_name: '',
    tone: 'friendly_professional',
    emergency_contact: '',
    // Step 4: CRM
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

  const handleFinish = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('ll_token');
      const body = {
        crm_type: config.crm_type === 'none' ? 'google_sheets' : config.crm_type,
        crm_api_key: config.crm_api_key || null,
        crm_tenant_id: config.crm_tenant_id || null,
        config: {
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
        },
      };

      const res = await fetch('/api/v1/dashboard/onboarding', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) throw new Error('Failed to save');

      localStorage.setItem('ll_onboarded', 'true');
      window.location.href = '/dashboard';
    } catch {
      setSaving(false);
    }
  };

  const canAdvance = () => {
    if (step === 0) return true;
    if (step === 1) return config.primary_services.length > 0;
    if (step === 2) return config.rep_name.trim().length > 0;
    if (step === 3) return true;
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
                  <label className={labelClass}>Open</label>
                  <input type="time" value={config.business_hours_start} onChange={e => updateConfig('business_hours_start', e.target.value)} className={inputClass} />
                </div>
                <div>
                  <label className={labelClass}>Close</label>
                  <input type="time" value={config.business_hours_end} onChange={e => updateConfig('business_hours_end', e.target.value)} className={inputClass} />
                </div>
              </div>

              <div>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.work_saturday}
                    onChange={e => updateConfig('work_saturday', e.target.checked)}
                    className="w-4 h-4 rounded border-[#222230] bg-[#1A1A24] text-orange-500 focus:ring-orange-500/20"
                  />
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
                <label className={labelClass}>After-hours handling</label>
                <select value={config.after_hours} onChange={e => updateConfig('after_hours', e.target.value)} className={`${inputClass} appearance-none`}>
                  <option value="ai_responds_books_next_available">AI responds & books next available slot</option>
                  <option value="ai_responds_owner_notified">AI responds & notifies you</option>
                  <option value="do_not_respond">Don't respond after hours</option>
                </select>
              </div>

              <div>
                <label className={labelClass}>Service radius (miles)</label>
                <input
                  type="number"
                  value={config.service_area_radius}
                  onChange={e => updateConfig('service_area_radius', e.target.value)}
                  className={inputClass}
                  placeholder="30"
                />
              </div>

              <div>
                <label className={labelClass}>Zip codes (optional, comma-separated)</label>
                <input
                  type="text"
                  value={config.service_area_zips}
                  onChange={e => updateConfig('service_area_zips', e.target.value)}
                  className={inputClass}
                  placeholder="10001, 10002, 10003"
                />
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
                      <button
                        key={service}
                        onClick={() => toggleService('primary_services', service)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                          selected
                            ? 'bg-orange-500/15 text-orange-400 border border-orange-500/30'
                            : 'bg-[#1A1A24] text-[#A1A1BC] border border-[#222230] hover:border-[#333340]'
                        }`}
                      >
                        {service}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className={labelClass}>Secondary services (optional)</label>
                <input
                  type="text"
                  value={config.secondary_services.join(', ')}
                  onChange={e => updateConfig('secondary_services', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  className={inputClass}
                  placeholder="Type additional services, comma-separated"
                />
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
                <label className={labelClass}>Agent name</label>
                <input
                  type="text"
                  value={config.rep_name}
                  onChange={e => updateConfig('rep_name', e.target.value)}
                  className={inputClass}
                  placeholder="e.g. Sarah, Mike, Alex"
                />
                <p className="text-xs text-[#52526B] mt-1.5">This name appears in SMS: "Hi! This is {config.rep_name || 'Sarah'} from {localStorage.getItem('ll_business') || 'your company'}."</p>
              </div>

              <div>
                <label className={labelClass}>Conversation tone</label>
                <div className="space-y-2">
                  {TONE_OPTIONS.map(opt => (
                    <label
                      key={opt.id}
                      className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                        config.tone === opt.id
                          ? 'border-orange-500/30 bg-orange-500/5'
                          : 'border-[#222230] hover:border-[#333340]'
                      }`}
                    >
                      <input
                        type="radio"
                        name="tone"
                        value={opt.id}
                        checked={config.tone === opt.id}
                        onChange={e => updateConfig('tone', e.target.value)}
                        className="mt-0.5 text-orange-500 focus:ring-orange-500/20"
                      />
                      <div>
                        <p className="text-sm font-medium text-[#F8F8FC]">{opt.label}</p>
                        <p className="text-xs text-[#52526B]">{opt.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className={labelClass}>Emergency contact phone</label>
                <input
                  type="tel"
                  value={config.emergency_contact}
                  onChange={e => updateConfig('emergency_contact', e.target.value)}
                  className={inputClass}
                  placeholder="(555) 123-4567"
                />
                <p className="text-xs text-[#52526B] mt-1.5">We'll route urgent leads here (gas leaks, flooding, no heat, etc.)</p>
              </div>
            </div>
          )}

          {/* ── Step 3: CRM ── */}
          {step === 3 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">Connect your CRM</h2>
                <p className="text-sm text-[#52526B]">We'll book appointments directly into your system.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {CRM_OPTIONS.map(crm => (
                  <button
                    key={crm.id}
                    onClick={() => updateConfig('crm_type', crm.id)}
                    className={`p-4 rounded-xl border text-left transition-all cursor-pointer ${
                      config.crm_type === crm.id
                        ? 'border-orange-500/30 bg-orange-500/5'
                        : 'border-[#222230] hover:border-[#333340]'
                    }`}
                  >
                    <p className="text-sm font-semibold text-[#F8F8FC]">{crm.name}</p>
                    <p className="text-xs text-[#52526B] mt-0.5">{crm.desc}</p>
                  </button>
                ))}
              </div>

              {config.crm_type && !['google_sheets', 'none'].includes(config.crm_type) && (
                <div className="space-y-4 pt-2">
                  <div>
                    <label className={labelClass}>API Key / Access Token</label>
                    <input
                      type="password"
                      value={config.crm_api_key}
                      onChange={e => updateConfig('crm_api_key', e.target.value)}
                      className={inputClass}
                      placeholder="Paste your API key"
                    />
                  </div>
                  <div>
                    <label className={labelClass}>Tenant / Account ID</label>
                    <input
                      type="text"
                      value={config.crm_tenant_id}
                      onChange={e => updateConfig('crm_tenant_id', e.target.value)}
                      className={inputClass}
                      placeholder="Your account ID"
                    />
                  </div>
                  <p className="text-xs text-[#52526B]">
                    Not sure where to find these? We'll help you connect after setup.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ── Step 4: Lead Sources ── */}
          {step === 4 && (
            <div className="space-y-6">
              <div className="text-center mb-2">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">Your lead source URLs</h2>
                <p className="text-sm text-[#52526B]">Point your lead sources to these webhook URLs to start receiving leads.</p>
              </div>

              <div className="space-y-3">
                {[
                  { label: 'Website Form', path: 'form', desc: 'Add to your website contact form action URL' },
                  { label: 'Google LSA', path: 'google-lsa', desc: 'Paste into Google Local Services webhook' },
                  { label: 'Facebook Leads', path: 'facebook', desc: 'Use as Facebook Lead Ads webhook' },
                  { label: 'Angi / HomeAdvisor', path: 'angi', desc: 'Configure in your Angi partner dashboard' },
                  { label: 'Missed Calls', path: 'missed-call', desc: 'Connect your call tracking provider' },
                ].map(source => {
                  const url = `${webhookBase}/${source.path}/${clientId}`;
                  return (
                    <div key={source.path} className="p-4 rounded-xl border border-[#222230] bg-[#111118]">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-semibold text-[#F8F8FC]">{source.label}</span>
                        <CopyButton text={url} />
                      </div>
                      <code className="text-xs text-orange-400/80 break-all block mb-1">{url}</code>
                      <p className="text-xs text-[#52526B]">{source.desc}</p>
                    </div>
                  );
                })}
              </div>

              <div className="p-4 rounded-xl bg-orange-500/5 border border-orange-500/20">
                <div className="flex items-start gap-3">
                  <Clock className="w-5 h-5 text-orange-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-[#F8F8FC]">Your SMS number</p>
                    <p className="text-xs text-[#A1A1BC] mt-1">
                      We'll provision a dedicated phone number for your business within 24 hours.
                      You'll receive an email once it's active and ready to receive leads.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-[#222230]">
            {step > 0 ? (
              <button
                onClick={() => setStep(s => s - 1)}
                className="flex items-center gap-2 text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
            ) : (
              <div />
            )}

            {step < STEPS.length - 1 ? (
              <button
                onClick={() => setStep(s => s + 1)}
                disabled={!canAdvance()}
                className="ld-btn-primary px-6 py-2.5 text-sm flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Continue <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleFinish}
                disabled={saving}
                className="ld-btn-primary px-6 py-2.5 text-sm flex items-center gap-2 disabled:opacity-50"
              >
                {saving ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>Go to Dashboard <ArrowRight className="w-4 h-4" /></>
                )}
              </button>
            )}
          </div>
        </div>

        <button
          onClick={() => navigate('/dashboard')}
          className="block mx-auto mt-6 text-xs text-[#52526B] hover:text-[#A1A1BC] transition-colors cursor-pointer"
        >
          Skip for now — I'll set this up later
        </button>
      </div>
    </div>
  );
}
