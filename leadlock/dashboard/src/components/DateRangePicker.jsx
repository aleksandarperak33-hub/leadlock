export default function DateRangePicker({ value, onChange, options = [] }) {
  return (
    <div className="flex rounded-lg p-0.5 bg-gray-100/80 border border-gray-200/60">
      {options.map(opt => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={`px-3 py-1 text-[11px] font-medium rounded-md transition-all duration-150 ${
            value === opt
              ? 'bg-white text-gray-900 shadow-sm'
              : 'text-gray-400 hover:text-gray-600'
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}
