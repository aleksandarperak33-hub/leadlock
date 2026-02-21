import { ChevronUp, ChevronDown } from 'lucide-react';

/**
 * DataTable -- Sortable data table with consistent styling, ARIA support, and loading state.
 *
 * @param {Array<{key: string, label: string, sortable?: boolean, render?: Function, align?: string}>} columns
 * @param {Array<Object>} data - Row data array
 * @param {string} [sortKey] - Currently sorted column key
 * @param {string} [sortDir='asc'] - Sort direction: asc | desc
 * @param {Function} [onSort] - Callback when a sortable header is clicked: (key) => void
 * @param {string} [emptyMessage='No data available'] - Message shown when data is empty
 * @param {Function} [onRowClick] - Optional row click handler: (row) => void
 * @param {boolean} [loading=false] - Show skeleton loading rows
 * @param {number} [loadingRows=5] - Number of skeleton rows when loading
 */
export default function DataTable({
  columns,
  data,
  sortKey,
  sortDir = 'asc',
  onSort,
  emptyMessage = 'No data available',
  onRowClick,
  loading = false,
  loadingRows = 5,
}) {
  const handleHeaderClick = (column) => {
    if (column.sortable && onSort) {
      onSort(column.key);
    }
  };

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl overflow-hidden shadow-sm">
      <table className="w-full">
        <thead>
          <tr className="bg-gray-50/80 border-b border-gray-200/60">
            {columns.map((column) => {
              const isSorted = sortKey === column.key;
              const SortIcon = isSorted && sortDir === 'desc' ? ChevronDown : ChevronUp;
              const alignClass = column.align === 'right' ? 'text-right' : 'text-left';
              const ariaSort = column.sortable && isSorted
                ? (sortDir === 'asc' ? 'ascending' : 'descending')
                : undefined;

              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={ariaSort}
                  className={`text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3 ${alignClass} ${
                    column.sortable ? 'cursor-pointer hover:text-gray-700 select-none' : ''
                  }`}
                  onClick={() => handleHeaderClick(column)}
                >
                  <span className="inline-flex items-center gap-1">
                    {column.label}
                    {column.sortable && isSorted && (
                      <SortIcon className="w-3.5 h-3.5 text-gray-400" />
                    )}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            [...Array(loadingRows)].map((_, i) => (
              <tr key={`skeleton-${i}`} className="border-b border-gray-100 last:border-0">
                {columns.map((column) => (
                  <td key={column.key} className="px-4 py-3.5">
                    <div className="h-4 bg-gray-100 rounded-lg animate-pulse" />
                  </td>
                ))}
              </tr>
            ))
          ) : data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="text-center py-12">
                <p className="text-sm text-gray-400">{emptyMessage}</p>
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => (
              <tr
                key={row.id || rowIndex}
                className={`border-b border-gray-100 last:border-0 hover:bg-gray-50/50 transition-colors ${
                  onRowClick ? 'cursor-pointer' : ''
                }`}
                onClick={() => onRowClick && onRowClick(row)}
              >
                {columns.map((column) => {
                  const cellValue = row[column.key];
                  const alignClass = column.align === 'right' ? 'text-right' : 'text-left';

                  return (
                    <td
                      key={column.key}
                      className={`text-sm text-gray-600 px-4 py-3.5 ${alignClass}`}
                    >
                      {column.render
                        ? column.render(cellValue, row)
                        : cellValue}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
