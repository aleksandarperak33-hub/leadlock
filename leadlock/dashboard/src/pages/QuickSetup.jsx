import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Zap, ArrowRight, Search, MapPin, Star, Phone, Globe,
  Loader2, AlertCircle, CheckCircle2, Building2,
} from 'lucide-react';
import { api } from '../api/client';

const PLACEHOLDER_URL = 'https://www.google.com/maps/place/Your+Business+Name';

export default function QuickSetup() {
  const navigate = useNavigate();
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [business, setBusiness] = useState(null);

  const handleLookup = async () => {
    const trimmed = url.trim();
    if (!trimmed) {
      setError('Please enter a Google Business Profile URL or your business name');
      return;
    }

    setLoading(true);
    setError('');
    setBusiness(null);

    try {
      const data = await api.gmbLookup(trimmed);
      if (data.success && data.business) {
        setBusiness(data.business);
      } else {
        setError(data.error || 'Could not find your business. Try a different URL or skip to set up manually.');
      }
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again or skip to set up manually.');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = () => {
    localStorage.setItem('ll_gmb_data', JSON.stringify(business));
    if (business.trade_type && business.trade_type !== 'other') {
      localStorage.setItem('ll_trade_type', business.trade_type);
    }
    if (business.business_name) {
      localStorage.setItem('ll_business', business.business_name);
    }
    if (business.phone) {
      localStorage.setItem('ll_owner_phone', business.phone);
    }
    navigate('/onboarding');
  };

  const handleSkip = () => {
    navigate('/onboarding');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !loading) {
      handleLookup();
    }
  };

  const inputClass = "w-full px-4 py-3.5 rounded-xl text-sm text-[#F8F8FC] bg-[#1A1A24] border border-[#222230] outline-none transition-all placeholder:text-[#52526B] focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20";

  return (
    <div className="landing-dark min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute top-[-20%] right-[-10%] w-[600px] h-[600px] rounded-full bg-orange-500/[0.04] blur-3xl" />
      <div className="absolute bottom-[-15%] left-[-10%] w-[500px] h-[500px] rounded-full bg-orange-500/[0.03] blur-3xl" />

      <div className="w-full max-w-[540px] relative z-10">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-orange-500 to-orange-600 shadow-lg shadow-orange-500/25">
            <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-2xl font-bold tracking-tight text-[#F8F8FC]">
            Lead<span className="text-orange-500">Lock</span>
          </span>
        </div>

        <div className="ld-card p-8">
          {!business ? (
            /* ── Search State ── */
            <div className="space-y-6">
              <div className="text-center">
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-2">Set up your account in seconds</h2>
                <p className="text-sm text-[#A1A1BC]">
                  Paste your Google Business Profile URL and we'll fill everything in.
                </p>
              </div>

              <div>
                <div className="relative">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#52526B]" />
                  <input
                    type="text"
                    value={url}
                    onChange={e => { setUrl(e.target.value); setError(''); }}
                    onKeyDown={handleKeyDown}
                    className={`${inputClass} pl-10`}
                    placeholder={PLACEHOLDER_URL}
                    autoFocus
                    disabled={loading}
                  />
                </div>
                <p className="text-xs text-[#52526B] mt-2">
                  Or just type your business name — we'll search for it.
                </p>
              </div>

              {error && (
                <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              <button
                onClick={handleLookup}
                disabled={loading || !url.trim()}
                className="w-full py-3.5 rounded-xl text-sm font-bold ld-btn-primary flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Finding your business...</>
                ) : (
                  <><Building2 className="w-4 h-4" /> Set Up My Account</>
                )}
              </button>
            </div>
          ) : (
            /* ── Confirmation State ── */
            <div className="space-y-6">
              <div className="text-center">
                <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-3" />
                <h2 className="text-xl font-bold text-[#F8F8FC] mb-1">We found your business</h2>
                <p className="text-sm text-[#A1A1BC]">Does this look right?</p>
              </div>

              {/* Business card */}
              <div className="p-5 rounded-xl bg-[#111118] border border-[#222230] space-y-3">
                <h3 className="text-lg font-bold text-[#F8F8FC]">{business.business_name}</h3>

                {business.trade_type && business.trade_type !== 'other' && (
                  <span className="inline-block px-2.5 py-0.5 rounded-full bg-orange-500/15 text-xs font-semibold uppercase tracking-wide text-orange-400">
                    {business.trade_type}
                  </span>
                )}

                <div className="space-y-2 text-sm">
                  {business.address && (
                    <div className="flex items-start gap-2 text-[#A1A1BC]">
                      <MapPin className="w-4 h-4 flex-shrink-0 mt-0.5 text-[#52526B]" />
                      <span>{business.address}</span>
                    </div>
                  )}
                  {business.phone && (
                    <div className="flex items-center gap-2 text-[#A1A1BC]">
                      <Phone className="w-4 h-4 flex-shrink-0 text-[#52526B]" />
                      <span>{business.phone}</span>
                    </div>
                  )}
                  {business.website && (
                    <div className="flex items-center gap-2 text-[#A1A1BC]">
                      <Globe className="w-4 h-4 flex-shrink-0 text-[#52526B]" />
                      <span className="truncate">{business.website}</span>
                    </div>
                  )}
                  {business.rating != null && (
                    <div className="flex items-center gap-2 text-[#A1A1BC]">
                      <Star className="w-4 h-4 flex-shrink-0 text-amber-400" />
                      <span>
                        {business.rating} rating
                        {business.reviews != null && <span className="text-[#52526B]"> ({business.reviews} reviews)</span>}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => { setBusiness(null); setUrl(''); }}
                  className="flex-1 py-3 rounded-xl text-sm font-semibold bg-[#1A1A24] border border-[#222230] text-[#A1A1BC] hover:border-[#333340] hover:text-[#F8F8FC] transition-all cursor-pointer"
                >
                  Not my business
                </button>
                <button
                  onClick={handleConfirm}
                  className="flex-1 py-3 rounded-xl text-sm font-bold ld-btn-primary flex items-center justify-center gap-2"
                >
                  Looks right <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>

        <button
          onClick={handleSkip}
          className="block mx-auto mt-6 text-xs text-[#52526B] hover:text-[#A1A1BC] transition-colors cursor-pointer"
        >
          Skip — I'll set up manually
        </button>
      </div>
    </div>
  );
}
