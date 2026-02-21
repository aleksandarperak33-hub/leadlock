import { useState } from 'react';
import { Phone, Search, Loader2 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { SectionHeader } from './SectionHeader';
import { INPUT_CLASSES } from './constants';

export default function PhoneProvisioningSection({ settings, onProvisioned }) {
  const { token } = useAuth();
  const [areaCode, setAreaCode] = useState('');
  const [numbers, setNumbers] = useState([]);
  const [searching, setSearching] = useState(false);
  const [provisioning, setProvisioning] = useState('');
  const [error, setError] = useState('');

  if (settings?.twilio_phone) {
    return (
      <div>
        <SectionHeader title="Phone Number" description="Your dedicated SMS line." />
        <div className="bg-green-50 border border-green-200/60 rounded-xl p-4 flex items-center gap-3">
          <Phone className="w-5 h-5 text-green-600" />
          <div>
            <p className="text-sm font-medium text-green-800">{settings.twilio_phone}</p>
            <p className="text-xs text-green-600">Active and receiving leads</p>
          </div>
        </div>
      </div>
    );
  }

  const handleSearch = async () => {
    if (!areaCode || areaCode.length !== 3) return;
    setSearching(true);
    setError('');
    setNumbers([]);
    try {
      const res = await fetch(`/api/v1/settings/available-numbers?area_code=${areaCode}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Search failed');
      setNumbers(data.numbers || []);
      if (!data.numbers?.length) setError('No numbers available for this area code');
    } catch (e) {
      setError(e.message);
    } finally {
      setSearching(false);
    }
  };

  const handleProvision = async (phoneNumber) => {
    setProvisioning(phoneNumber);
    setError('');
    try {
      const res = await fetch('/api/v1/settings/provision-number', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ phone_number: phoneNumber }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Provisioning failed');
      onProvisioned(data.phone_number, data);
    } catch (e) {
      setError(e.message);
    } finally {
      setProvisioning('');
    }
  };

  return (
    <div>
      <SectionHeader title="Phone Number" description="Get a dedicated SMS line for your business." />
      <div className="flex gap-3 mb-4">
        <input
          id="area-code"
          type="text"
          value={areaCode}
          onChange={(e) => setAreaCode(e.target.value.replace(/\D/g, '').slice(0, 3))}
          placeholder="Area code (e.g. 512)"
          className={`${INPUT_CLASSES} max-w-[160px]`}
        />
        <button
          onClick={handleSearch}
          disabled={searching || areaCode.length !== 3}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer"
        >
          {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          Search
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-red-50 border border-red-200/60 text-red-600 text-sm">
          {error}
        </div>
      )}

      {numbers.length > 0 && (
        <div className="space-y-2">
          {numbers.map((num) => (
            <div key={num.phone_number} className="flex items-center justify-between p-3 bg-gray-50 border border-gray-200/60 rounded-xl">
              <div>
                <p className="text-sm font-medium text-gray-900">{num.friendly_name}</p>
                <p className="text-xs text-gray-400">{num.locality}, {num.region}</p>
              </div>
              <button
                onClick={() => handleProvision(num.phone_number)}
                disabled={!!provisioning}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer"
              >
                {provisioning === num.phone_number ? 'Provisioning...' : 'Select'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
