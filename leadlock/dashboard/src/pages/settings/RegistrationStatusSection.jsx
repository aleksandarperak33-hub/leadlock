import { Clock, CheckCircle2, Loader2, XCircle, Building2 } from 'lucide-react';
import { SectionHeader } from './SectionHeader';
import BusinessRegistrationForm from './BusinessRegistrationForm';

export default function RegistrationStatusSection({ settings, setSettings }) {
  const status = settings?.ten_dlc_status || 'pending';
  const needsInfo = status === 'collecting_info' && !settings?.business_type;

  return (
    <div>
      <SectionHeader
        title="SMS Registration"
        description="Your number must be registered before it can send outbound SMS."
      />
      <RegistrationStatusBanner status={status} />
      {needsInfo && (
        <BusinessRegistrationForm settings={settings} setSettings={setSettings} />
      )}
    </div>
  );
}

function RegistrationStatusBanner({ status }) {
  if (status === 'active') {
    return (
      <div className="flex items-center gap-3 p-4 rounded-xl bg-green-50 border border-green-200/60">
        <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-green-800">Registration Active</p>
          <p className="text-xs text-green-600">Your number is fully registered and can send SMS.</p>
        </div>
      </div>
    );
  }

  if (status.endsWith('_rejected')) {
    return (
      <div className="flex items-center gap-3 p-4 rounded-xl bg-red-50 border border-red-200/60">
        <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-red-800">Registration Rejected</p>
          <p className="text-xs text-red-600">
            Your registration was rejected. Please contact support for assistance.
          </p>
        </div>
      </div>
    );
  }

  if (status === 'collecting_info') {
    return (
      <div className="flex items-center gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200/60 mb-6">
        <Building2 className="w-5 h-5 text-amber-600 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-amber-800">Business Info Required</p>
          <p className="text-xs text-amber-600">
            Submit your business details below to register your number for SMS.
          </p>
        </div>
      </div>
    );
  }

  // Pending states
  const progressSteps = [
    { key: 'profile', label: 'Profile' },
    { key: 'brand', label: 'Brand' },
    { key: 'campaign', label: 'Campaign' },
  ];

  const isTollFree = status.startsWith('tf_');

  const getStepState = (stepKey) => {
    const completedAfter = {
      profile: ['brand_pending', 'brand_approved', 'campaign_pending', 'active'],
      brand: ['campaign_pending', 'active'],
      campaign: ['active'],
    };
    const stateOrder = {
      profile: ['profile_pending', 'profile_approved'],
      brand: ['brand_pending', 'brand_approved'],
      campaign: ['campaign_pending'],
    };

    if (completedAfter[stepKey]?.includes(status)) return 'completed';
    if (stateOrder[stepKey]?.includes(status)) return 'current';
    return 'pending';
  };

  return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-blue-50 border border-blue-200/60">
      <Clock className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
      <div className="flex-1">
        <p className="text-sm font-medium text-blue-800">Registration In Progress</p>
        <p className="text-xs text-blue-600 mb-3">
          {isTollFree
            ? 'Your toll-free number is being verified. This typically takes 1-3 business days.'
            : 'Your number is being registered with carriers. This typically takes 1-5 business days.'}
        </p>

        {!isTollFree && (
          <div className="flex items-center gap-2">
            {progressSteps.map((step, i) => {
              const state = getStepState(step.key);
              return (
                <div key={step.key} className="flex items-center gap-2">
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                    state === 'completed' ? 'bg-green-100 text-green-700' :
                    state === 'current' ? 'bg-blue-100 text-blue-700' :
                    'bg-gray-100 text-gray-400'
                  }`}>
                    {state === 'completed' && <CheckCircle2 className="w-3 h-3" />}
                    {state === 'current' && <Loader2 className="w-3 h-3 animate-spin" />}
                    {step.label}
                  </div>
                  {i < progressSteps.length - 1 && (
                    <div className={`w-4 h-px ${
                      state === 'completed' ? 'bg-green-300' : 'bg-gray-200'
                    }`} />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
