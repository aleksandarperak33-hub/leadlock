import { X, Plus } from 'lucide-react';

const TRADE_TYPES = ['hvac', 'plumbing', 'roofing', 'electrical', 'solar', 'general'];

const INPUT_CLASSES = 'bg-white border border-gray-200 text-gray-900 outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-100 transition-all';

/**
 * SettingsTab -- Sales Engine configuration panel.
 * Manages target locations, trade types, rate limits, and email sender config.
 */
export default function SalesEngineSettings({
  config,
  onConfigChange,
  newLocation,
  onNewLocationChange,
  onAddLocation,
  onRemoveLocation,
  onToggleTradeType,
  onSave,
  saving,
}) {
  if (!config) return null;

  return (
    <div className="max-w-2xl space-y-6">
      {/* Target Locations */}
      <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card">
        <p className="text-lg font-semibold text-gray-900 mb-4">Target Locations</p>
        <div className="flex flex-wrap gap-2 mb-4">
          {(config.target_locations || []).map((loc, i) => (
            <span key={i} className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs bg-gray-50 text-gray-600 border border-gray-200/50 font-medium">
              {loc.city}, {loc.state}
              <button onClick={() => onRemoveLocation(i)} className="ml-0.5 text-gray-400 hover:text-gray-600 cursor-pointer">
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={newLocation.city}
            onChange={(e) => onNewLocationChange({ ...newLocation, city: e.target.value })}
            className={`flex-1 px-3 py-2.5 rounded-xl text-sm ${INPUT_CLASSES}`}
            placeholder="City"
          />
          <input
            type="text"
            value={newLocation.state}
            onChange={(e) => onNewLocationChange({ ...newLocation, state: e.target.value.toUpperCase().slice(0, 2) })}
            className={`w-16 px-3 py-2.5 rounded-xl text-sm ${INPUT_CLASSES}`}
            placeholder="ST"
            maxLength={2}
          />
          <button
            onClick={onAddLocation}
            className="flex items-center gap-1 px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 cursor-pointer transition-colors"
          >
            <Plus className="w-3.5 h-3.5" /> Add
          </button>
        </div>
      </div>

      {/* Target Trade Types */}
      <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card">
        <p className="text-lg font-semibold text-gray-900 mb-4">Target Trade Types</p>
        <div className="flex flex-wrap gap-2">
          {TRADE_TYPES.map((trade) => {
            const active = (config.target_trade_types || []).includes(trade);
            return (
              <button
                key={trade}
                onClick={() => onToggleTradeType(trade)}
                className={`px-4 py-2 rounded-xl text-sm font-medium capitalize transition-all cursor-pointer ${
                  active
                    ? 'bg-orange-50 text-orange-700 border border-orange-200/60'
                    : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300'
                }`}
              >
                {trade}
              </button>
            );
          })}
        </div>
      </div>

      {/* Limits */}
      <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card">
        <p className="text-lg font-semibold text-gray-900 mb-4">Rate Limits</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Daily Emails', key: 'daily_email_limit' },
            { label: 'Daily Scrapes', key: 'daily_scrape_limit' },
            { label: 'Delay (hours)', key: 'sequence_delay_hours' },
            { label: 'Max Steps', key: 'max_sequence_steps' },
          ].map(({ label, key }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">{label}</label>
              <input
                type="number"
                value={config[key] || ''}
                onChange={(e) => {
                  const raw = e.target.value;
                  onConfigChange({ ...config, [key]: raw === '' ? '' : (parseInt(raw) || 0) });
                }}
                className={`w-full px-3 py-2.5 rounded-xl text-sm font-mono ${INPUT_CLASSES}`}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Email Sender Config */}
      <div className="bg-white border border-gray-200/50 rounded-2xl p-6 shadow-card">
        <p className="text-lg font-semibold text-gray-900 mb-4">Email Sender Config</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            { label: 'From Email', key: 'from_email', placeholder: 'outreach@leadlock.io' },
            { label: 'From Name', key: 'from_name', placeholder: 'LeadLock' },
            { label: 'Reply-To Email', key: 'reply_to_email', placeholder: 'alex@leadlock.io' },
            { label: 'Company Address', key: 'company_address', placeholder: '123 Main St, Austin, TX 78701' },
          ].map(({ label, key, placeholder }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">{label}</label>
              <input
                type="text"
                value={config[key] || ''}
                onChange={(e) => onConfigChange({ ...config, [key]: e.target.value })}
                className={`w-full px-3 py-2.5 rounded-xl text-sm ${INPUT_CLASSES}`}
                placeholder={placeholder}
              />
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={onSave}
        disabled={saving}
        className="px-6 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors disabled:opacity-50 cursor-pointer"
      >
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  );
}
