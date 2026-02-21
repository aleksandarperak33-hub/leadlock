import { useState } from 'react';
import { Shield, Loader2, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { INPUT_CLASSES, LABEL_CLASSES, BUSINESS_TYPE_OPTIONS } from './constants';

export default function BusinessRegistrationForm({ settings, setSettings }) {
  const { token } = useAuth();
  const [businessType, setBusinessType] = useState(settings?.business_type || '');
  const [businessEin, setBusinessEin] = useState(settings?.business_ein || '');
  const [businessWebsite, setBusinessWebsite] = useState(settings?.business_website || '');
  const [street, setStreet] = useState(settings?.business_address?.street || '');
  const [city, setCity] = useState(settings?.business_address?.city || '');
  const [addrState, setAddrState] = useState(settings?.business_address?.state || '');
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
      const res = await fetch('/api/v1/settings/business-registration', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          business_type: businessType,
          business_ein: businessEin,
          business_website: businessWebsite,
          business_address: { street, city, state: addrState, zip },
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
        business_address: { street, city, state: addrState, zip },
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
        <label htmlFor="business-type" className={LABEL_CLASSES}>Business Type *</label>
        <select
          id="business-type"
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
        <label htmlFor="business-ein" className={LABEL_CLASSES}>
          EIN / Tax ID {businessType === 'sole_proprietorship' ? '(optional)' : ''}
        </label>
        <input
          id="business-ein"
          type="text"
          value={businessEin}
          onChange={(e) => setBusinessEin(e.target.value.replace(/[^\d-]/g, '').slice(0, 11))}
          className={INPUT_CLASSES}
          placeholder="XX-XXXXXXX"
        />
      </div>

      <div>
        <label htmlFor="business-website" className={LABEL_CLASSES}>Business Website</label>
        <input
          id="business-website"
          type="url"
          value={businessWebsite}
          onChange={(e) => setBusinessWebsite(e.target.value)}
          className={INPUT_CLASSES}
          placeholder="https://yourcompany.com"
        />
      </div>

      <div>
        <label htmlFor="business-street" className={LABEL_CLASSES}>Business Address</label>
        <div className="space-y-3">
          <input
            id="business-street"
            type="text"
            value={street}
            onChange={(e) => setStreet(e.target.value)}
            className={INPUT_CLASSES}
            placeholder="Street address"
          />
          <div className="grid grid-cols-3 gap-3">
            <input
              id="business-city"
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className={INPUT_CLASSES}
              placeholder="City"
            />
            <input
              id="business-state"
              type="text"
              value={addrState}
              onChange={(e) => setAddrState(e.target.value.toUpperCase().slice(0, 2))}
              className={INPUT_CLASSES}
              placeholder="State"
            />
            <input
              id="business-zip"
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
