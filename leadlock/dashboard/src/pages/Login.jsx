import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { AlertCircle, Zap } from 'lucide-react';

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const data = await api.login(email, password);
      localStorage.setItem('ll_token', data.token);
      localStorage.setItem('ll_business', data.business_name);
      localStorage.setItem('ll_is_admin', data.is_admin ? 'true' : 'false');
      navigate('/');
    } catch (err) {
      setError('Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden" style={{ background: '#06080d' }}>
      {/* Ambient gradient orbs */}
      <div className="animate-float" style={{
        position: 'fixed', top: '-10%', right: '-5%', width: '500px', height: '500px',
        background: 'radial-gradient(circle, rgba(99, 102, 241, 0.12) 0%, transparent 70%)',
        borderRadius: '50%', pointerEvents: 'none',
      }} />
      <div className="animate-float-delay" style={{
        position: 'fixed', bottom: '-15%', left: '-10%', width: '600px', height: '600px',
        background: 'radial-gradient(circle, rgba(139, 92, 246, 0.08) 0%, transparent 70%)',
        borderRadius: '50%', pointerEvents: 'none',
      }} />
      <div className="animate-float-slow" style={{
        position: 'fixed', top: '40%', left: '50%', width: '400px', height: '400px',
        background: 'radial-gradient(circle, rgba(99, 102, 241, 0.06) 0%, transparent 70%)',
        borderRadius: '50%', pointerEvents: 'none', transform: 'translateX(-50%)',
      }} />

      {/* Dot grid background */}
      <div className="fixed inset-0 opacity-[0.02]" style={{
        backgroundImage: 'radial-gradient(circle at 1px 1px, rgb(148 163 184) 0.5px, transparent 0)',
        backgroundSize: '32px 32px',
      }} />

      <div className="w-full max-w-[400px] relative z-10 animate-fade-up">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-10">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center gradient-btn" style={{ boxShadow: '0 4px 20px rgba(99, 102, 241, 0.3)' }}>
            <Zap className="w-4.5 h-4.5 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-xl font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>
            Lead<span className="gradient-text">Lock</span>
          </span>
        </div>

        {/* Card */}
        <div className="glass-card gradient-border p-8" style={{ background: 'rgba(15, 17, 24, 0.7)' }}>
          <h2 className="text-lg font-semibold text-center mb-1" style={{ color: 'var(--text-primary)' }}>
            Welcome back
          </h2>
          <p className="text-[13px] text-center mb-8" style={{ color: 'var(--text-tertiary)' }}>
            Sign in to your dashboard
          </p>

          {error && (
            <div
              className="mb-5 px-4 py-3 rounded-xl flex items-center gap-2.5 text-[13px]"
              style={{
                background: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.12)',
                color: '#f87171',
              }}
            >
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--text-tertiary)' }}>
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl text-[13px] outline-none glass-input"
                style={{ color: 'var(--text-primary)' }}
                placeholder="you@company.com"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--text-tertiary)' }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl text-[13px] outline-none glass-input"
                style={{ color: 'var(--text-primary)' }}
                placeholder={'\u2022'.repeat(10)}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl text-[13px] font-semibold text-white gradient-btn disabled:opacity-50 disabled:transform-none"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </div>

        <p className="text-center text-[11px] mt-8 font-medium" style={{ color: 'var(--text-tertiary)' }}>
          Powered by <span className="gradient-text">LeadLock AI</span>
        </p>
      </div>
    </div>
  );
}
