import { useRef, useCallback } from 'react';

/**
 * Tabs -- Horizontal tab navigation with animated underline indicator.
 * Includes ARIA roles and keyboard navigation (arrow keys).
 *
 * @param {Array<{id: string, label: string, count?: number}>} tabs
 * @param {string} activeId - Currently active tab ID
 * @param {Function} onChange - Callback when a tab is clicked: (tabId) => void
 */
export default function Tabs({ tabs, activeId, onChange }) {
  const tabRefs = useRef({});

  const handleKeyDown = useCallback((e, currentIndex) => {
    let nextIndex = currentIndex;

    if (e.key === 'ArrowRight') {
      e.preventDefault();
      nextIndex = (currentIndex + 1) % tabs.length;
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    } else if (e.key === 'Home') {
      e.preventDefault();
      nextIndex = 0;
    } else if (e.key === 'End') {
      e.preventDefault();
      nextIndex = tabs.length - 1;
    } else {
      return;
    }

    const nextTab = tabs[nextIndex];
    onChange(nextTab.id);
    tabRefs.current[nextTab.id]?.focus();
  }, [tabs, onChange]);

  return (
    <div
      className="flex items-center gap-0.5 border-b border-gray-200/50 mb-6"
      role="tablist"
    >
      {tabs.map((tab, index) => {
        const isActive = tab.id === activeId;

        return (
          <button
            key={tab.id}
            ref={(el) => { tabRefs.current[tab.id] = el; }}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            role="tab"
            aria-selected={isActive}
            tabIndex={isActive ? 0 : -1}
            className={`px-4 py-2.5 text-sm font-medium cursor-pointer transition-colors relative ${
              isActive
                ? 'text-gray-900'
                : 'text-gray-400 hover:text-gray-600'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className={`text-[11px] ml-1.5 font-mono ${isActive ? 'text-gray-500' : 'text-gray-300'}`}>
                {tab.count}
              </span>
            )}
            {isActive && (
              <span className="absolute bottom-0 left-2 right-2 h-[2px] bg-gray-900 rounded-full" />
            )}
          </button>
        );
      })}
    </div>
  );
}
