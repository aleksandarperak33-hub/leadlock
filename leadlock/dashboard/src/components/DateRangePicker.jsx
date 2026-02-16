export default function DateRangePicker({ value, onChange, options = [] }) {
  return (
    <div className="flex rounded-lg p-0.5" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
      {options.map(opt => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className="px-3 py-1 text-[11px] font-medium rounded-md transition-all duration-150"
          style={{
            background: value === opt ? 'var(--surface-3)' : 'transparent',
            color: value === opt ? 'var(--text-primary)' : 'var(--text-tertiary)',
          }}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}
