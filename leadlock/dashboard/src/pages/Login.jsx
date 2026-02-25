import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { AlertCircle, Zap, ArrowRight } from 'lucide-react';
import SEO from '../components/SEO';

export default function Login() {
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
      localStorage.setItem('ll_client_id', data.client_id);
      window.location.href = '/dashboard';
    } catch (err) {
      setError('Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#FAFAFA] animate-[fade-up_0.4s_ease-out]">
      <SEO
        title="Login"
        description="Sign in to your LeadLock dashboard to manage leads, view analytics, and configure your AI speed-to-lead platform."
        path="/login"
      />

      <div className="w-full max-w-[400px]">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-9 h-9 rounded-xl bg-orange-500 flex items-center justify-center">
            <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-xl font-semibold text-gray-900">
            LeadLock
          </span>
        </div>

        {/* Card */}
        <div className="bg-white border border-gray-200/50 rounded-2xl p-8 shadow-card">
          <h2 className="text-lg font-semibold text-center text-gray-900 mb-1">
            Welcome back
          </h2>
          <p className="text-sm text-center text-gray-400 mb-6">
            Sign in to your dashboard
          </p>

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl flex items-center gap-2.5 text-sm bg-red-50 border border-red-200/60 text-red-600">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="login-email" className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl text-sm text-gray-900 bg-white border border-gray-200 outline-none transition-all placeholder:text-gray-400 focus:border-orange-300 focus:ring-2 focus:ring-orange-100"
                placeholder="you@company.com"
              />
            </div>
            <div>
              <label htmlFor="login-password" className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl text-sm text-gray-900 bg-white border border-gray-200 outline-none transition-all placeholder:text-gray-400 focus:border-orange-300 focus:ring-2 focus:ring-orange-100"
                placeholder={'\u2022'.repeat(10)}
              />
            </div>
            <div className="flex justify-end">
              <Link
                to="/forgot-password"
                className="text-xs text-orange-500 hover:text-orange-600 font-medium"
              >
                Forgot password?
              </Link>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Signing in...
                </span>
              ) : (
                <>Sign In <ArrowRight className="w-4 h-4" /></>
              )}
            </button>
          </form>
        </div>

        <p className="text-xs text-gray-400 text-center mt-8">
          Powered by <span className="text-orange-500 font-semibold">LeadLock AI</span>
        </p>
      </div>
    </div>
  );
}
