/**
 * PageHeader — Standard page header with title, optional subtitle, and action slot.
 *
 * @param {string} title - Page title text
 * @param {string} [subtitle] - Optional subtitle text
 * @param {JSX.Element} [actions] - Optional action buttons rendered on the right
 */
export default function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex justify-between items-start mb-8">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-gray-900">
          {title}
        </h1>
        {subtitle && (
          <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
        )}
      </div>
      {actions && <div>{actions}</div>}
    </div>
  );
}
