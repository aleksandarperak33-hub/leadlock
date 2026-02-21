import { X, Keyboard } from 'lucide-react';

/**
 * ShortcutHelpModal — Displays available keyboard shortcuts.
 */
export default function ShortcutHelpModal({ shortcuts, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-black/20 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative bg-white rounded-2xl shadow-xl max-w-sm w-full border border-gray-200/60 animate-fade-up">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Keyboard className="w-4 h-4 text-gray-400" />
            <h3 className="text-base font-semibold text-gray-900">
              Keyboard Shortcuts
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 cursor-pointer"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-1">
          {shortcuts.map(({ keys, label }) => (
            <div
              key={keys}
              className="flex items-center justify-between py-2"
            >
              <span className="text-sm text-gray-600">{label}</span>
              <div className="flex items-center gap-1">
                {keys.split(' ').map((key) => (
                  <kbd
                    key={key}
                    className="inline-flex items-center justify-center min-w-[24px] h-6 px-1.5 bg-gray-100 border border-gray-200 rounded-md text-xs font-mono font-medium text-gray-600"
                  >
                    {key === 'Escape' ? 'Esc' : key}
                  </kbd>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="px-6 py-4 border-t border-gray-100 bg-gray-50/50 rounded-b-2xl">
          <p className="text-xs text-gray-400">
            Press <kbd className="px-1 py-0.5 bg-gray-100 border border-gray-200 rounded text-xs font-mono">?</kbd> to toggle this dialog
          </p>
        </div>
      </div>
    </div>
  );
}
