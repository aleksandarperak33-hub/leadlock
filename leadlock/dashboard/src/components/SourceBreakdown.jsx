import { SOURCE_BAR_PALETTE } from '../lib/colors';

/**
 * Label mapping for source keys.
 */
const SOURCE_LABELS = {
  google_lsa: 'Google LSA',
  angi: 'Angi',
  facebook: 'Facebook',
  website: 'Website',
  missed_call: 'Missed Call',
  text_in: 'Text-In',
  thumbtack: 'Thumbtack',
  referral: 'Referral',
  yelp: 'Yelp',
};

/**
 * SourceBreakdown -- Horizontal bar chart showing lead sources.
 * Parent wraps in a card container; this component renders only the content.
 *
 * @param {Object} data - Map of source key to count
 */
export default function SourceBreakdown({ data = {} }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);

  if (!entries.length) {
    return (
      <p className="text-sm text-gray-400 py-8 text-center">
        No data available
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {entries.map(([source, count], index) => {
        const pct = total > 0 ? ((count / total) * 100).toFixed(0) : 0;
        const barColor = SOURCE_BAR_PALETTE[index % SOURCE_BAR_PALETTE.length];

        return (
          <div key={source}>
            <div className="flex items-center justify-between text-sm mb-1.5">
              <span className="text-gray-600 font-medium">
                {SOURCE_LABELS[source] || source}
              </span>
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono text-gray-400">
                  {pct}%
                </span>
                <span className="text-sm font-mono font-semibold text-gray-900">
                  {count}
                </span>
              </div>
            </div>
            <div className="w-full rounded-lg h-2 bg-gray-100 overflow-hidden">
              <div
                className="h-2 rounded-lg transition-all duration-700 ease-out"
                style={{
                  width: `${(count / max) * 100}%`,
                  background: barColor,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
