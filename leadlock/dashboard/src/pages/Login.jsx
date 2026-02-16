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
    <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-gray-50 via-white to-indigo-50/30">
      <div className="w-full max-w-[400px]">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-10">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-indigo-500 shadow-lg shadow-indigo-500/20">
            <Zap className="w-4.5 h-4.5 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-xl font-bold tracking-tight text-gray-900">
            Lead<span className="text-indigo-500">Lock</span>
          </span>
        </div>

        {/* Card */}
        <div className="bg-white border border-gray-200 rounded-2xl p-8 shadow-lg shadow-gray-900/[0.04]">
          <h2 className="text-lg font-semibold text-center mb-1 text-gray-900">
            Welcome back
          </h2>
          <p className="text-sm text-center mb-8 text-gray-500">
            Sign in to your dashboard
          </p>

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl flex items-center gap-2.5 text-sm bg-red-50 border border-red-100 text-red-600">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2 text-gray-500">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-lg text-sm text-gray-900 bg-white border border-gray-200 outline-none transition-all placeholder:text-gray-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                placeholder="you@company.com"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2 text-gray-500">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-lg text-sm text-gray-900 bg-white border border-gray-200 outline-none transition-all placeholder:text-gray-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                placeholder={'\u2022'.repeat(10)}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg text-sm font-semibold text-white bg-indigo-500 hover:bg-indigo-600 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-sm shadow-indigo-500/20"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs mt-8 font-medium text-gray-400">
          Powered by <span className="text-indigo-500">LeadLock AI</span>
        </p>
      </div>
    </div>
  );
}
