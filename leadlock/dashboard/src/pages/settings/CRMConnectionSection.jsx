import { useState } from 'react';
import { Plug, Loader2 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { SectionHeader } from './SectionHeader';
import { INPUT_CLASSES, LABEL_CLASSES, CRM_OPTIONS } from './constants';

export default function CRMConnectionSection({ settings }) {
  const { token } = useAuth();
  const [crmType, setCrmType] = useState(settings?.crm_type || 'google_sheets');
  const [apiKey, setApiKey] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/v1/integrations/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ crm_type: crmType, api_key: apiKey, tenant_id: tenantId }),
      });
      const data = await res.json();
      setTestResult(data);
    } catch (e) {
      setTestResult({ connected: false, message: e.message });
    } finally {
      setTesting(false);
    }
  };

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const res = await fetch('/api/v1/integrations/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ crm_type: crmType, api_key: apiKey, tenant_id: tenantId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Connection failed');
      setTestResult({ connected: true, message: 'CRM connected successfully!' });
    } catch (e) {
      setTestResult({ connected: false, message: e.message });
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div>
      <SectionHeader title="CRM Integration" description="Connect your CRM for automatic booking sync." />
      <div className="space-y-4">
        <div>
          <label htmlFor="crm-platform" className={LABEL_CLASSES}>CRM Platform</label>
          <select
            id="crm-platform"
            value={crmType}
            onChange={(e) => { setCrmType(e.target.value); setTestResult(null); }}
            className={`${INPUT_CLASSES} cursor-pointer`}
          >
            {CRM_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {crmType !== 'google_sheets' && (
          <>
            <div>
              <label htmlFor="crm-api-key" className={LABEL_CLASSES}>API Key</label>
              <input
                id="crm-api-key"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className={INPUT_CLASSES}
                placeholder="Enter your API key"
              />
            </div>
            {crmType === 'gohighlevel' && (
              <div>
                <label htmlFor="crm-location-id" className={LABEL_CLASSES}>Location ID</label>
                <input
                  id="crm-location-id"
                  type="text"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  className={INPUT_CLASSES}
                  placeholder="Your GoHighLevel location ID"
                />
              </div>
            )}
            <div className="flex gap-3">
              <button
                onClick={handleTest}
                disabled={testing || !apiKey}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium border border-gray-200 hover:bg-gray-50 text-gray-700 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />}
                Test Connection
              </button>
              <button
                onClick={handleConnect}
                disabled={connecting || !apiKey || !testResult?.connected}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50 transition-colors cursor-pointer"
              >
                {connecting ? 'Connecting...' : 'Connect'}
              </button>
            </div>
          </>
        )}

        {testResult && (
          <div className={`px-4 py-3 rounded-xl text-sm ${
            testResult.connected
              ? 'bg-green-50 border border-green-200/60 text-green-700'
              : 'bg-red-50 border border-red-200/60 text-red-600'
          }`}>
            {testResult.message}
            {testResult.technicians_found > 0 && (
              <span className="ml-2 text-xs">({testResult.technicians_found} team members found)</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
