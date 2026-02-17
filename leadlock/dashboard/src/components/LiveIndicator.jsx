/**
 * LiveIndicator -- Animated green dot with pulse effect and status label.
 *
 * @param {string} [label='System Active'] - Text label next to the indicator
 */
export default function LiveIndicator({ label = 'System Active' }) {
  return (
    <div className="flex items-center gap-2">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-[live-pulse_2s_ease-in-out_infinite]" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
      </span>
      <span className="text-xs font-medium text-gray-400">{label}</span>
    </div>
  );
}
