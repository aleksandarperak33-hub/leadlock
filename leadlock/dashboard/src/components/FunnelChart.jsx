/**
 * FunnelChart - Visual conversion funnel with decreasing-width bars.
 *
 * @param {Object} stages - Object mapping stage_name -> count, or array of {stage, count} objects
 * @param {string} [className] - Optional additional class names
 */
export default function FunnelChart({ stages, className = '' }) {
  if (!stages) return null;

  const entries = Array.isArray(stages)
    ? stages.map((s) => [s.stage ?? s.name ?? String(s), Number(s.count ?? s.value ?? 0)])
    : Object.entries(stages).map(([k, v]) => [k, Number(v)]);

  if (entries.length === 0) {
    return (
      <p className="text-sm text-gray-400 text-center py-4">No funnel data available.</p>
    );
  }

  const topCount = entries[0]?.[1] || 1;

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {entries.map(([stage, count], index) => {
        const pct = topCount > 0 ? Math.round((count / topCount) * 100) : 0;
        const convFromPrev =
          index > 0 && entries[index - 1][1] > 0
            ? Math.round((count / entries[index - 1][1]) * 100)
            : null;

        const minWidth = 30;
        const barWidth = Math.max(pct, minWidth);

        const gradientStart = Math.max(95 - index * 15, 40);
        const gradientEnd = Math.max(80 - index * 12, 30);

        return (
          <div key={stage} className="flex flex-col items-center">
            <div
              className="flex items-center justify-center rounded-xl py-3 px-4 transition-all duration-500"
              style={{
                width: `${barWidth}%`,
                background: `linear-gradient(135deg, hsl(25, 95%, ${gradientStart}%) 0%, hsl(20, 90%, ${gradientEnd}%) 100%)`,
              }}
            >
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-white capitalize">
                  {stage.replace(/_/g, ' ')}
                </span>
                <span className="text-sm font-mono font-bold text-white/90">
                  {count.toLocaleString()}
                </span>
                <span className="text-xs text-white/75">({pct}%)</span>
              </div>
            </div>

            {convFromPrev !== null && (
              <div className="flex items-center gap-1 my-1">
                <div className="w-px h-3 bg-gray-300" />
                <span className="text-xs text-gray-400 font-mono">{convFromPrev}% converted</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
