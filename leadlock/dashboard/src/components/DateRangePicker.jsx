export default function DateRangePicker({ value, onChange, options = [] }) {
  return (
    <div className="flex bg-slate-800 rounded-lg p-0.5">
      {options.map(opt => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            value === opt ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}
