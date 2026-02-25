/**
 * Variant-to-class mapping for badge colors.
 */
const VARIANT_CLASSES = {
  success: 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/10',
  warning: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/10',
  danger: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/10',
  info: 'bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-600/10',
  neutral: 'bg-gray-50 text-gray-600 ring-1 ring-inset ring-gray-500/10',
};

/**
 * Size-to-class mapping for badge dimensions.
 */
const SIZE_CLASSES = {
  sm: 'text-[11px] px-2 py-0.5 rounded-md font-medium',
  md: 'text-xs px-2.5 py-1 rounded-lg font-medium',
};

/**
 * Badge - Small inline status indicator with color variants.
 *
 * @param {string} [variant='neutral'] - Color variant: success | warning | danger | info | neutral
 * @param {string} [size='sm'] - Size variant: sm | md
 * @param {React.ReactNode} children - Badge content
 */
export default function Badge({ variant = 'neutral', size = 'sm', children }) {
  const variantClass = VARIANT_CLASSES[variant] || VARIANT_CLASSES.neutral;
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.sm;

  return (
    <span className={`inline-flex items-center whitespace-nowrap ${sizeClass} ${variantClass}`}>
      {children}
    </span>
  );
}
