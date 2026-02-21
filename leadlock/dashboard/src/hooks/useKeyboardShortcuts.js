import { useEffect, useCallback, useState } from 'react';

/**
 * Keyboard shortcut definitions.
 * Chord shortcuts use 'g' as the leader key (e.g. g then d = Dashboard).
 */
const SHORTCUTS = [
  { keys: 'g d', label: 'Go to Dashboard', path: '/dashboard' },
  { keys: 'g l', label: 'Go to Leads', path: '/leads' },
  { keys: 'g c', label: 'Go to Conversations', path: '/conversations' },
  { keys: 'g b', label: 'Go to Bookings', path: '/bookings' },
  { keys: 'g r', label: 'Go to Reports', path: '/reports' },
  { keys: 'g s', label: 'Go to Settings', path: '/settings' },
  { keys: '/', label: 'Focus search', action: 'focus-search' },
  { keys: '?', label: 'Show shortcuts', action: 'show-help' },
  { keys: 'Escape', label: 'Close modal / blur', action: 'escape' },
];

/**
 * Returns true if the event target is an input, textarea, select, or contenteditable.
 */
function isEditable(target) {
  if (!target) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
}

/**
 * useKeyboardShortcuts - Registers global keyboard shortcuts.
 *
 * @param {Function} navigate - react-router navigate function
 * @returns {{ showHelp: boolean, setShowHelp: Function, shortcuts: Array }}
 */
export function useKeyboardShortcuts(navigate) {
  const [showHelp, setShowHelp] = useState(false);
  const [leaderKey, setLeaderKey] = useState(null);
  const [leaderTimer, setLeaderTimer] = useState(null);

  const clearLeader = useCallback(() => {
    setLeaderKey(null);
    if (leaderTimer) {
      clearTimeout(leaderTimer);
      setLeaderTimer(null);
    }
  }, [leaderTimer]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      // Escape always works, even in inputs
      if (e.key === 'Escape') {
        if (showHelp) {
          setShowHelp(false);
          e.preventDefault();
          return;
        }
        // Blur the active element
        if (document.activeElement && document.activeElement !== document.body) {
          document.activeElement.blur();
          e.preventDefault();
        }
        clearLeader();
        return;
      }

      // Skip shortcuts when typing in form elements
      if (isEditable(e.target)) return;

      // Skip if modifier keys are held (allow normal browser shortcuts)
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      // Leader key chord: 'g' starts a chord
      if (e.key === 'g' && !leaderKey) {
        e.preventDefault();
        setLeaderKey('g');
        const timer = setTimeout(() => {
          setLeaderKey(null);
        }, 800);
        setLeaderTimer(timer);
        return;
      }

      // Chord completion
      if (leaderKey === 'g') {
        const chord = `g ${e.key}`;
        const match = SHORTCUTS.find((s) => s.keys === chord);
        if (match && match.path) {
          e.preventDefault();
          navigate(match.path);
        }
        clearLeader();
        return;
      }

      // Single-key shortcuts
      if (e.key === '/') {
        e.preventDefault();
        const searchInput = document.querySelector(
          '[data-search-input], input[type="search"], input[placeholder*="Search"]'
        );
        if (searchInput) {
          searchInput.focus();
        }
        return;
      }

      if (e.key === '?') {
        e.preventDefault();
        setShowHelp((prev) => !prev);
        return;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [navigate, leaderKey, leaderTimer, showHelp, clearLeader]);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (leaderTimer) clearTimeout(leaderTimer);
    };
  }, [leaderTimer]);

  return { showHelp, setShowHelp, shortcuts: SHORTCUTS };
}
