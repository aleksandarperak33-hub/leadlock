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
    <div className="admin-theme flex h-screen overflow-hidden bg-[#f8f9fb]">
      {/* Sidebar */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-[240px] flex flex-col bg-white border-r border-gray-200
        transform transition-transform duration-300 ease-in-out
        lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Logo */}
        <div className="flex items-center justify-between px-5 h-16 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center gradient-btn" style={{ boxShadow: 'none', padding: 0 }}>
              <Zap className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[14px] font-bold tracking-tight text-gray-900">
                Lead<span className="gradient-text">Lock</span>
              </span>
              <span className="text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded-md bg-violet-50 text-violet-600 border border-violet-100">
                Admin
              </span>
            </div>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden text-gray-400 hover:text-gray-600 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) => `
                flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 cursor-pointer
                ${isActive ? 'bg-violet-50 text-gray-900' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'}
              `}
            >
              {({ isActive }) => (
                <>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${isActive ? 'bg-violet-100' : ''}`}>
                    <Icon className="w-[18px] h-[18px]" strokeWidth={isActive ? 2 : 1.5}
                      style={{ color: isActive ? '#7c3aed' : undefined }} />
                  </div>
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* System status */}
        <div className="mx-3 mb-3 px-3 py-2.5 rounded-xl bg-violet-50 border border-violet-100">
          <div className="flex items-center gap-2">
            <div className="relative">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-live-pulse" />
              <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-500 animate-glow-ring" />
            </div>
            <span className="text-[11px] font-semibold text-gray-500">System Active</span>
          </div>
        </div>

        {/* Logout */}
        <div className="px-3 py-3 border-t border-gray-100">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 w-full px-3 py-2.5 text-[13px] font-medium rounded-xl transition-all duration-200 text-gray-400 hover:bg-gray-50 hover:text-gray-600 cursor-pointer"
          >
            <LogOut className="w-[18px] h-[18px]" strokeWidth={1.5} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        {/* Mobile header */}
        <div className="lg:hidden flex items-center gap-3 px-4 h-14 sticky top-0 z-30 bg-white/90 backdrop-blur-sm border-b border-gray-200">
          <button onClick={() => setSidebarOpen(true)} className="text-gray-500 cursor-pointer">
            <Menu className="w-5 h-5" />
          </button>
          <span className="text-[13px] font-bold tracking-tight text-gray-900">
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
