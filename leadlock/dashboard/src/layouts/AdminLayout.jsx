import { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Users, FileText, DollarSign,
  Target, Activity, LogOut, Menu, X, Shield
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/clients', icon: Users, label: 'Clients' },
  { to: '/leads', icon: FileText, label: 'All Leads' },
  { to: '/revenue', icon: DollarSign, label: 'Revenue' },
  { to: '/outreach', icon: Target, label: 'Outreach' },
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
        fixed inset-y-0 left-0 z-50 w-[220px] flex flex-col
        transform transition-transform duration-200 ease-in-out
        lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `} style={{ background: 'var(--surface-1)', borderRight: '1px solid var(--border)' }}>

        {/* Logo */}
        <div className="flex items-center justify-between px-5 h-14" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-md flex items-center justify-center" style={{ background: 'var(--accent)' }}>
              <span className="text-white text-xs font-bold tracking-tight">L</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>LeadLock</span>
              <span className="text-[9px] font-semibold uppercase tracking-widest px-1.5 py-0.5 rounded" style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}>Admin</span>
            </div>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden" style={{ color: 'var(--text-tertiary)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-3 space-y-0.5">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setSidebarOpen(false)}
              className="flex items-center gap-2.5 px-2.5 py-[7px] rounded-md text-[13px] font-medium transition-all duration-150"
              style={({ isActive }) => ({
                color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
                background: isActive ? 'var(--surface-3)' : 'transparent',
              })}
            >
              <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* System status */}
        <div className="mx-3 mb-2 px-3 py-2 rounded-md" style={{ background: 'rgba(124, 91, 240, 0.06)', border: '1px solid rgba(124, 91, 240, 0.1)' }}>
          <div className="flex items-center gap-1.5">
            <Activity className="w-3 h-3" style={{ color: 'rgba(124, 91, 240, 0.7)' }} />
            <span className="text-[11px] font-medium" style={{ color: 'rgba(124, 91, 240, 0.7)' }}>System Active</span>
          </div>
        </div>

        {/* Logout */}
        <div className="px-3 py-2.5" style={{ borderTop: '1px solid var(--border)' }}>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2.5 w-full px-2.5 py-[7px] text-[13px] font-medium rounded-md transition-colors"
            style={{ color: 'var(--text-tertiary)' }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-tertiary)'}
          >
            <LogOut className="w-4 h-4" strokeWidth={1.75} />
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
        <div className="lg:hidden flex items-center gap-3 px-4 h-12 sticky top-0 z-30" style={{ background: 'var(--surface-1)', borderBottom: '1px solid var(--border)' }}>
          <button onClick={() => setSidebarOpen(true)} style={{ color: 'var(--text-tertiary)' }}>
            <Menu className="w-5 h-5" />
          </button>
          <span className="text-[13px] font-semibold tracking-tight">LeadLock Admin</span>
        </div>

        <div className="p-5 lg:p-8 max-w-[1200px] mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
