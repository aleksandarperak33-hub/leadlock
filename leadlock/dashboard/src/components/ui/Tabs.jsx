/**
 * Tabs — Horizontal tab navigation with animated underline indicator.
 *
 * @param {Array<{id: string, label: string, count?: number}>} tabs - Tab definitions
 * @param {string} activeId - Currently active tab ID
 * @param {Function} onChange - Callback when a tab is clicked: (tabId) => void
 */
export default function Tabs({ tabs, activeId, onChange }) {
  return (
    <div className="flex items-center gap-1 border-b border-gray-200/60 mb-6">
      {tabs.map((tab) => {
        const isActive = tab.id === activeId;

        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium cursor-pointer transition-colors relative ${
              isActive
                ? 'text-orange-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className="text-xs text-gray-400 ml-1.5">{tab.count}</span>
            )}
            {isActive && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-orange-500 rounded-full" />
            )}
          </button>
        );
      })}
    </div>
  );
}
