import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Smart pagination with truncation (e.g. 1 ... 4 5 [6] 7 8 ... 20).
 *
 * @param {number} page - Current page (1-indexed)
 * @param {number} pages - Total pages
 * @param {Function} onChange - Callback: (pageNumber) => void
 */
export default function Pagination({ page, pages, onChange }) {
  if (pages <= 1) return null;

  const getPageNumbers = () => {
    const items = [];
    const delta = 2;
    const rangeStart = Math.max(2, page - delta);
    const rangeEnd = Math.min(pages - 1, page + delta);

    items.push(1);

    if (rangeStart > 2) {
      items.push('ellipsis-start');
    }

    for (let i = rangeStart; i <= rangeEnd; i++) {
      items.push(i);
    }

    if (rangeEnd < pages - 1) {
      items.push('ellipsis-end');
    }

    if (pages > 1) {
      items.push(pages);
    }

    return items;
  };

  return (
    <nav
      className="flex items-center justify-between mt-4"
      role="navigation"
      aria-label="Pagination"
    >
      <span className="text-sm font-mono text-gray-400">
        Page {page} of {pages}
      </span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed"
          aria-label="Previous page"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        {getPageNumbers().map((item) => {
          if (typeof item === 'string') {
            return (
              <span
                key={item}
                className="w-8 h-8 flex items-center justify-center text-gray-400 text-sm"
                aria-hidden="true"
              >
                &hellip;
              </span>
            );
          }

          const isCurrent = page === item;
          return (
            <button
              key={item}
              onClick={() => onChange(item)}
              className={`w-8 h-8 rounded-lg text-sm font-medium cursor-pointer transition-colors ${
                isCurrent
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
              }`}
              aria-label={`Page ${item}`}
              aria-current={isCurrent ? 'page' : undefined}
            >
              {item}
            </button>
          );
        })}

        <button
          onClick={() => onChange(Math.min(pages, page + 1))}
          disabled={page === pages}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer disabled:cursor-not-allowed"
          aria-label="Next page"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </nav>
  );
}
