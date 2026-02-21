/**
 * EmptyState - Centered placeholder for empty data sections.
 *
 * @param {import('lucide-react').LucideIcon} icon - Lucide icon component
 * @param {string} title - Empty state title
 * @param {string} description - Explanatory description text
 * @param {JSX.Element} [action] - Optional action element (e.g. a button)
 */
export default function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      {Icon && <Icon className="w-12 h-12 text-gray-300 mb-4" />}
      <p className="text-sm font-medium text-gray-900 mb-1">{title}</p>
      <p className="text-sm text-gray-400 mb-4">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
}
