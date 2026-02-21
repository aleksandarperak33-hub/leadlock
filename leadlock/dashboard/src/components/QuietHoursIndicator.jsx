import { Moon, Sun } from 'lucide-react';

export default function QuietHoursIndicator() {
  const hour = new Date().getHours();
  const isQuietHours = hour < 8 || hour >= 21;

  if (isQuietHours) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/[0.08] border border-amber-500/15">
        <Moon className="w-4 h-4 text-amber-400" />
        <span className="text-[11px] font-medium text-amber-400">Quiet Hours Active</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/[0.08] border border-emerald-500/15">
      <Sun className="w-4 h-4 text-emerald-400" />
      <span className="text-[11px] font-medium text-emerald-400">Active Hours</span>
    </div>
  );
}
