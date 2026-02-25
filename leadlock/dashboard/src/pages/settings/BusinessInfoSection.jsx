import { SectionHeader } from './SectionHeader';

function getDisplayStatus(status) {
  const map = {
    pending: 'Not Started',
    collecting_info: 'Info Needed',
    profile_pending: 'In Review',
    profile_approved: 'In Review',
    profile_rejected: 'Action Required',
    brand_pending: 'In Review',
    brand_approved: 'Almost Ready',
    brand_rejected: 'Action Required',
    campaign_pending: 'Almost Ready',
    campaign_rejected: 'Action Required',
    tf_verification_pending: 'In Review',
    tf_rejected: 'Action Required',
    active: 'Active',
  };
  return map[status] || status || 'Not Started';
}

export default function BusinessInfoSection({ settings }) {
  const fields = [
    { label: 'Business Name', value: settings?.business_name },
    { label: 'Trade Type', value: settings?.trade_type, capitalize: true },
    { label: 'Twilio Number', value: settings?.twilio_phone || 'Not assigned' },
    { label: 'Registration', value: getDisplayStatus(settings?.ten_dlc_status), capitalize: true },
  ];

  return (
    <div>
      <SectionHeader
        title="Business Information"
        description="Read-only details about your account."
      />
      <div className="bg-gray-50 border border-gray-200/50 rounded-xl p-4">
        <div className="grid grid-cols-2 gap-5">
          {fields.map(({ label, value, capitalize }) => (
            <div key={label}>
              <span className="text-xs text-gray-400">{label}</span>
              <p
                className={`text-sm mt-0.5 font-medium text-gray-900 ${
                  capitalize ? 'capitalize' : ''
                }`}
              >
                {value || '\u2014'}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
