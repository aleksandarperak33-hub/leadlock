import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Zap, Check, AlertCircle, ArrowRight } from 'lucide-react';

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [status, setStatus] = useState('loading'); // loading | success | error
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage('Invalid verification link. No token provided.');
      return;
    }

    const verify = async () => {
      try {
        const res = await fetch(`/api/v1/auth/verify-email/${token}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Verification failed');
        setStatus('success');
        setMessage(data.message || 'Email verified successfully!');
      } catch (err) {
        setStatus('error');
        setMessage(err.message);
      }
    };

    verify();
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#FAFAFA]">
      <div className="w-full max-w-[400px]">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-9 h-9 rounded-xl bg-orange-500 flex items-center justify-center">
            <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-xl font-semibold text-gray-900">LeadLock</span>
        </div>

        {/* Card */}
        <div className="bg-white border border-gray-200/50 rounded-2xl p-8 shadow-card text-center">
          {status === 'loading' && (
            <>
              <div className="w-10 h-10 border-3 border-orange-200 border-t-orange-500 rounded-full animate-spin mx-auto mb-4" />
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Verifying your email...</h2>
              <p className="text-sm text-gray-400">This will only take a moment.</p>
            </>
          )}

          {status === 'success' && (
            <>
              <div className="w-12 h-12 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
                <Check className="w-6 h-6 text-green-500" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900 mb-2">{message}</h2>
              <p className="text-sm text-gray-500 mb-6">
                Your account is ready. Head to your dashboard to get started.
              </p>
              <Link
                to="/dashboard"
                className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold text-white bg-orange-500 hover:bg-orange-600 transition-colors"
              >
                Go to Dashboard <ArrowRight className="w-4 h-4" />
              </Link>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
                <AlertCircle className="w-6 h-6 text-red-400" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900 mb-2">Verification Failed</h2>
              <p className="text-sm text-gray-500 mb-6">{message}</p>
              <Link
                to="/dashboard"
                className="text-sm text-orange-500 hover:text-orange-600 font-medium"
              >
                Go to Dashboard
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
