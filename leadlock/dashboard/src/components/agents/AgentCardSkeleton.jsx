/**
 * Skeleton loader that matches AgentCard's exact shape.
 * Used during initial fleet data load.
 */
export default function AgentCardSkeleton() {
  return (
    <div className="glass-card p-5 animate-pulse">
      <div className="flex items-start justify-between mb-3">
        <div className="w-9 h-9 rounded-lg bg-gray-200" />
        <div className="w-2.5 h-2.5 rounded-full bg-gray-200" />
      </div>
      <div className="h-4 w-28 bg-gray-200 rounded mb-1.5" />
      <div className="h-3 w-20 bg-gray-100 rounded mb-4" />
      <div className="flex items-center justify-between">
        <div className="h-3 w-14 bg-gray-100 rounded" />
        <div className="h-3 w-16 bg-gray-100 rounded" />
        <div className="h-3 w-12 bg-gray-100 rounded" />
      </div>
    </div>
  );
}
