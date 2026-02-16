import { Moon, Sun } from 'lucide-react';

export default function QuietHoursIndicator() {
  const hour = new Date().getHours();
  const isQuietHours = hour < 8 || hour >= 21;

  if (isQuietHours) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg" style={{
        background: 'rgba(245, 158, 11, 0.08)',
        border: '1px solid rgba(245, 158, 11, 0.15)',
      }}>
        <Moon className="w-4 h-4" style={{ color: '#fbbf24' }} />
        <span className="text-[11px] font-medium" style={{ color: '#fbbf24' }}>Quiet Hours Active</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg" style={{
      background: 'rgba(16, 185, 129, 0.08)',
      border: '1px solid rgba(16, 185, 129, 0.15)',
    }}>
      <Sun className="w-4 h-4" style={{ color: '#34d399' }} />
      <span className="text-[11px] font-medium" style={{ color: '#34d399' }}>Active Hours</span>
    </div>
  );
}
