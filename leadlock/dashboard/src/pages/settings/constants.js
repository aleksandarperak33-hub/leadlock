export const INPUT_CLASSES =
  'w-full px-4 py-2.5 text-sm bg-white border border-gray-200 rounded-xl outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100 placeholder:text-gray-400 text-gray-900 transition-all';

export const LABEL_CLASSES = 'text-sm font-medium text-gray-700 mb-1.5 block';

export const TONE_OPTIONS = [
  { value: 'friendly_professional', label: 'Friendly Professional' },
  { value: 'casual', label: 'Casual' },
  { value: 'formal', label: 'Formal' },
];

export const AFTER_HOURS_OPTIONS = [
  { value: 'ai_responds_books_next_available', label: 'AI responds, books next available' },
  { value: 'ai_responds_owner_notified', label: 'AI responds, owner notified' },
  { value: 'do_not_respond', label: 'Do not respond until business hours' },
];

export const CRM_OPTIONS = [
  { value: 'servicetitan', label: 'ServiceTitan' },
  { value: 'housecallpro', label: 'Housecall Pro' },
  { value: 'jobber', label: 'Jobber' },
  { value: 'gohighlevel', label: 'GoHighLevel' },
  { value: 'google_sheets', label: 'Google Sheets' },
];

export const BUSINESS_TYPE_OPTIONS = [
  { value: 'sole_proprietorship', label: 'Sole Proprietorship' },
  { value: 'llc', label: 'LLC' },
  { value: 'corporation', label: 'Corporation' },
  { value: 'partnership', label: 'Partnership' },
];
