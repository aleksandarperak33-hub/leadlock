import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { AlertCircle, Zap, ArrowRight, Building2 } from 'lucide-react';

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

export default function Signup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    business_name: '',
    name: '',
    email: '',
    phone: '',
    trade_type: '',
    password: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const updateField = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/v1/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Signup failed' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      localStorage.setItem('ll_token', data.token);
      localStorage.setItem('ll_business', data.business_name);
      localStorage.setItem('ll_is_admin', data.is_admin ? 'true' : 'false');
      navigate('/dashboard');
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="landing-dark min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background decorations */}
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
            Start your free trial
          </h2>
          <p className="text-sm text-center mb-8 text-[#52526B]">
            14 days free. No credit card required.
          </p>

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl flex items-center gap-2.5 text-sm bg-red-500/10 border border-red-500/20 text-red-400">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Business Name
              </label>
              <input
                type="text"
                value={form.business_name}
                onChange={e => updateField('business_name', e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border border-[#222230] outline-none transition-all placeholder:text-[#52526B] focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20"
                placeholder="Apex HVAC Solutions"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                  Your Name
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => updateField('name', e.target.value)}
                  required
                  className="w-full px-4 py-3 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border border-[#222230] outline-none transition-all placeholder:text-[#52526B] focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20"
                  placeholder="John Smith"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                  Trade Type
                </label>
                <select
                  value={form.trade_type}
                  onChange={e => updateField('trade_type', e.target.value)}
                  required
                  className="w-full px-4 py-3 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border border-[#222230] outline-none transition-all focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 appearance-none"
                >
                  <option value="" disabled>Select trade</option>
                  {TRADE_TYPES.map(t => (
                    <option key={t} value={t.toLowerCase()}>{t}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Email
              </label>
              <input
                type="email"
                value={form.email}
                onChange={e => updateField('email', e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border border-[#222230] outline-none transition-all placeholder:text-[#52526B] focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20"
                placeholder="john@apexhvac.com"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Phone
              </label>
              <input
                type="tel"
                value={form.phone}
                onChange={e => updateField('phone', e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border border-[#222230] outline-none transition-all placeholder:text-[#52526B] focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20"
                placeholder="(555) 123-4567"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2 text-[#52526B]">
                Password
              </label>
              <input
                type="password"
                value={form.password}
                onChange={e => updateField('password', e.target.value)}
                required
                minLength={8}
                className="w-full px-4 py-3 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border border-[#222230] outline-none transition-all placeholder:text-[#52526B] focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20"
                placeholder={'\u2022'.repeat(10)}
              />
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
