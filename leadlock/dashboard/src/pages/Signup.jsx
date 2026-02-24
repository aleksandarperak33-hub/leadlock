import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { AlertCircle, Zap, ArrowRight, CheckCircle2 } from 'lucide-react';

const TRADE_TYPES = [
  'HVAC',
  'Plumbing',
  'Electrical',
  'Roofing',
  'Solar',
  'General Contractor',
  'Landscaping',
  'Pest Control',
  'Other',
];

function FieldError({ message }) {
  if (!message) return null;
  return <p className="text-xs text-red-400 mt-1">{message}</p>;
}

export default function Signup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    business_name: '',
    name: '',
    email: '',
    phone: '',
    trade_type: '',
    password: '',
    password_confirm: '',
    tos_accepted: false,
  });
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);

  const updateField = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
    // Clear field error on change
    if (fieldErrors[field]) {
      setFieldErrors(prev => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const validate = () => {
    const errors = {};
    if (!form.business_name.trim()) errors.business_name = 'Business name is required';
    if (!form.name.trim()) errors.name = 'Your name is required';
    if (!form.email.trim()) {
      errors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      errors.email = 'Enter a valid email address';
    }
    if (!form.phone.trim()) errors.phone = 'Phone is required';
    if (!form.trade_type) errors.trade_type = 'Select your trade';
    if (form.password.length < 8) {
      errors.password = 'Password must be at least 8 characters';
    }
    if (form.password !== form.password_confirm) {
      errors.password_confirm = 'Passwords do not match';
    }
    if (!form.tos_accepted) {
      errors.tos_accepted = 'You must accept the Terms of Service';
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!validate()) return;
    setLoading(true);

    try {
      const res = await fetch('/api/v1/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          business_name: form.business_name,
          name: form.name,
          email: form.email,
          phone: form.phone,
          trade_type: form.trade_type,
          password: form.password,
          tos_accepted: form.tos_accepted,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Signup failed' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      localStorage.setItem('ll_token', data.token);
      localStorage.setItem('ll_business', data.business_name);
      localStorage.setItem('ll_is_admin', data.is_admin ? 'true' : 'false');
      localStorage.setItem('ll_client_id', data.client_id);
      localStorage.setItem('ll_trade_type', form.trade_type);
      localStorage.setItem('ll_onboarding_status', data.onboarding_status || 'pending');
      localStorage.setItem('ll_owner_phone', form.phone);
      window.location.href = '/onboarding';
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const inputClass = (field) => {
    const base = "w-full px-4 py-3 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border outline-none transition-all placeholder:text-[#52526B] focus:ring-2";
    return fieldErrors[field]
      ? `${base} border-red-500/50 focus:border-red-500 focus:ring-red-500/20`
      : `${base} border-[#222230] focus:border-orange-500 focus:ring-orange-500/20`;
  };

  return (
    <div className="landing-dark min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute top-[-20%] right-[-10%] w-[600px] h-[600px] rounded-full bg-orange-500/[0.04] blur-3xl" />
      <div className="absolute bottom-[-15%] left-[-10%] w-[500px] h-[500px] rounded-full bg-blue-500/[0.03] blur-3xl" />

      <div className="w-full max-w-[480px] relative z-10">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-orange-500 to-orange-600 shadow-lg shadow-orange-500/25">
            <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-2xl font-bold tracking-tight text-[#F8F8FC]">
            Lead<span className="text-orange-500">Lock</span>
          </span>
        </div>

        {/* Card */}
        <div className="ld-card p-8">
          <h2 className="text-xl font-bold text-center mb-1 text-[#F8F8FC]">
            Get started with LeadLock
          </h2>
          <p className="text-sm text-center mb-8 text-[#52526B]">
            Set up your account in 2 minutes.
          </p>

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl flex items-center gap-2.5 text-sm bg-red-500/10 border border-red-500/20 text-red-400">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="signup-business" className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Business Name
              </label>
              <input
                id="signup-business"
                type="text"
                value={form.business_name}
                onChange={e => updateField('business_name', e.target.value)}
                className={inputClass('business_name')}
                placeholder="Apex HVAC Solutions"
              />
              <FieldError message={fieldErrors.business_name} />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="signup-name" className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                  Your Name
                </label>
                <input
                  id="signup-name"
                  type="text"
                  value={form.name}
                  onChange={e => updateField('name', e.target.value)}
                  className={inputClass('name')}
                  placeholder="John Smith"
                />
                <FieldError message={fieldErrors.name} />
              </div>
              <div>
                <label htmlFor="signup-trade" className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                  Trade Type
                </label>
                <select
                  id="signup-trade"
                  value={form.trade_type}
                  onChange={e => updateField('trade_type', e.target.value)}
                  className={`${inputClass('trade_type')} appearance-none`}
                >
                  <option value="" disabled>Select trade</option>
                  {TRADE_TYPES.map(t => (
                    <option key={t} value={t.toLowerCase()}>{t}</option>
                  ))}
                </select>
                <FieldError message={fieldErrors.trade_type} />
              </div>
            </div>

            <div>
              <label htmlFor="signup-email" className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Email
              </label>
              <input
                id="signup-email"
                type="email"
                value={form.email}
                onChange={e => updateField('email', e.target.value)}
                className={inputClass('email')}
                placeholder="john@apexhvac.com"
              />
              <FieldError message={fieldErrors.email} />
            </div>

            <div>
              <label htmlFor="signup-phone" className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Phone
              </label>
              <input
                id="signup-phone"
                type="tel"
                value={form.phone}
                onChange={e => updateField('phone', e.target.value)}
                className={inputClass('phone')}
                placeholder="(555) 123-4567"
              />
              <FieldError message={fieldErrors.phone} />
            </div>

            <div>
              <label htmlFor="signup-password" className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Password
              </label>
              <input
                id="signup-password"
                type="password"
                value={form.password}
                onChange={e => updateField('password', e.target.value)}
                className={inputClass('password')}
                placeholder={'\u2022'.repeat(10)}
              />
              <FieldError message={fieldErrors.password} />
            </div>

            <div>
              <label htmlFor="signup-password-confirm" className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Confirm Password
              </label>
              <input
                id="signup-password-confirm"
                type="password"
                value={form.password_confirm}
                onChange={e => updateField('password_confirm', e.target.value)}
                className={inputClass('password_confirm')}
                placeholder={'\u2022'.repeat(10)}
              />
              <FieldError message={fieldErrors.password_confirm} />
            </div>

            {/* Terms of Service */}
            <div>
              <label className={`flex items-start gap-3 cursor-pointer ${fieldErrors.tos_accepted ? '' : ''}`}>
                <input
                  type="checkbox"
                  checked={form.tos_accepted}
                  onChange={e => updateField('tos_accepted', e.target.checked)}
                  className="w-4 h-4 mt-0.5 rounded border-[#222230] bg-[#1A1A24] text-orange-500 focus:ring-orange-500/20"
                />
                <span className="text-sm text-[#A1A1BC]">
                  I agree to the{' '}
                  <Link to="/terms" className="text-orange-400 hover:text-orange-300 underline" target="_blank">
                    Terms of Service
                  </Link>
                  {' '}and{' '}
                  <Link to="/privacy" className="text-orange-400 hover:text-orange-300 underline" target="_blank">
                    Privacy Policy
                  </Link>
                </span>
              </label>
              <FieldError message={fieldErrors.tos_accepted} />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 rounded-xl text-sm font-semibold ld-btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Creating account...
                </span>
              ) : (
                <>Create Account <ArrowRight className="w-4 h-4" /></>
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-sm mt-6 text-[#52526B]">
          Already have an account?{' '}
          <Link to="/login" className="text-orange-400 hover:text-orange-300 font-medium transition-colors">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
