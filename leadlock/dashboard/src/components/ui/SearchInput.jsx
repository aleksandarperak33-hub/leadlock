import { Search, X } from 'lucide-react';

/**
 * SearchInput — Search text field with icon and clear button.
 *
 * @param {string} value - Current search value
 * @param {Function} onChange - Change handler: (newValue) => void
 * @param {string} [placeholder='Search...'] - Placeholder text
 */
export default function SearchInput({
  value,
  onChange,
  placeholder = 'Search...',
}) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-9 pr-9 py-2.5 text-sm bg-white border border-gray-200 rounded-xl outline-none transition-all focus:border-orange-300 focus:ring-2 focus:ring-orange-100 placeholder:text-gray-400"
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
