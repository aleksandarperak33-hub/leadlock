/**
 * Color-to-class mapping for status dots.
 */
const COLOR_CLASSES = {
  green: 'bg-emerald-500',
  yellow: 'bg-amber-500',
  red: 'bg-red-500',
  gray: 'bg-gray-300',
};

/**
 * StatusDot - Small colored circle indicator for status display.
 *
 * @param {string} [color='gray'] - Dot color: green | yellow | red | gray
 */
export default function StatusDot({ color = 'gray' }) {
  const colorClass = COLOR_CLASSES[color] || COLOR_CLASSES.gray;

  return <span className={`w-2 h-2 rounded-full inline-block ${colorClass}`} />;
}
