import { Moon, Sun } from 'lucide-react';

export default function QuietHoursIndicator() {
  const hour = new Date().getHours();
  const isQuietHours = hour < 8 || hour >= 21;

  if (isQuietHours) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-500/10 border border-amber-500/20 rounded-lg">
        <Moon className="w-4 h-4 text-amber-400" />
        <span className="text-xs text-amber-400 font-medium">Quiet Hours Active</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
      <Sun className="w-4 h-4 text-emerald-400" />
      <span className="text-xs text-emerald-400 font-medium">Active Hours</span>
    </div>
  );
}
