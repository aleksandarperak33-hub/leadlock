import { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Users, FileText, DollarSign,
  Target, Zap, Activity, LogOut, Menu, X, Send, LineChart
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/clients', icon: Users, label: 'Clients' },
  { to: '/leads', icon: FileText, label: 'All Leads' },
  { to: '/revenue', icon: DollarSign, label: 'Revenue' },
  { to: '/outreach', icon: Target, label: 'Outreach' },
  { to: '/sales-engine', icon: Zap, label: 'Sales Engine' },
  { to: '/campaigns', icon: Send, label: 'Campaigns' },
  { to: '/insights', icon: LineChart, label: 'Insights' },
];

export default function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('ll_token');
    localStorage.removeItem('ll_business');
    localStorage.removeItem('ll_is_admin');
    navigate('/login');
  };

  return (
    <div className="admin-theme flex h-screen overflow-hidden" style={{ background: 'var(--surface-0)' }}>
      {/* Sidebar */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-[240px] flex flex-col glass-sidebar
        transform transition-transform duration-300 ease-in-out
        lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Logo */}
        <div className="flex items-center justify-between px-5 h-16" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center gradient-btn" style={{ boxShadow: 'none', padding: 0 }}>
              <Zap className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[14px] font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>
                Lead<span className="gradient-text">Lock</span>
              </span>
              <span className="text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded-md" style={{
                background: 'linear-gradient(135deg, rgba(124, 58, 237, 0.15), rgba(168, 85, 247, 0.1))',
                color: '#a855f7',
                border: '1px solid rgba(168, 85, 247, 0.15)',
              }}>Admin</span>
            </div>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden" style={{ color: 'var(--text-tertiary)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) => `
                flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200
                ${isActive ? 'nav-active' : 'hover:bg-white/[0.03]'}
              `}
              style={({ isActive }) => ({
                color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
              })}
            >
              {({ isActive }) => (
                <>
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors" style={{
                    background: isActive ? 'rgba(124, 58, 237, 0.12)' : 'transparent',
                  }}>
                    <Icon className="w-[18px] h-[18px]" strokeWidth={isActive ? 2 : 1.5} style={{
                      color: isActive ? '#a855f7' : 'inherit',
                    }} />
                  </div>
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* System status */}
        <div className="mx-3 mb-3 px-3 py-2.5 rounded-xl" style={{
          background: 'linear-gradient(135deg, rgba(124, 58, 237, 0.06), rgba(168, 85, 247, 0.03))',
          border: '1px solid rgba(124, 58, 237, 0.08)',
        }}>
          <div className="flex items-center gap-2">
            <div className="relative">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-live-pulse" />
              <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-400 animate-glow-ring" />
            </div>
            <span className="text-[11px] font-semibold" style={{ color: 'var(--text-tertiary)' }}>System Active</span>
          </div>
        </div>

        {/* Logout */}
        <div className="px-3 py-3" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.04)' }}>
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 w-full px-3 py-2.5 text-[13px] font-medium rounded-xl transition-all duration-200 hover:bg-white/[0.03]"
            style={{ color: 'var(--text-tertiary)' }}
          >
            <LogOut className="w-[18px] h-[18px]" strokeWidth={1.5} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        {/* Mobile header */}
        <div className="lg:hidden flex items-center gap-3 px-4 h-14 sticky top-0 z-30 glass" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
          <button onClick={() => setSidebarOpen(true)} style={{ color: 'var(--text-tertiary)' }}>
            <Menu className="w-5 h-5" />
          </button>
          <span className="text-[13px] font-bold tracking-tight">
            Lead<span className="gradient-text">Lock</span> Admin
          </span>
        </div>

        <div className="p-5 lg:p-8 max-w-[1200px] mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
