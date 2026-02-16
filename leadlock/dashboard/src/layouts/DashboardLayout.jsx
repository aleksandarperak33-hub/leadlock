import { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Users, MessageSquare, BarChart3,
  Settings, LogOut, Menu, X, Shield, Zap, Calendar
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/leads', icon: Users, label: 'Leads' },
  { to: '/conversations', icon: MessageSquare, label: 'Conversations' },
  { to: '/bookings', icon: Calendar, label: 'Bookings' },
  { to: '/reports', icon: BarChart3, label: 'Reports' },
  { to: '/compliance', icon: Shield, label: 'Compliance' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const businessName = localStorage.getItem('ll_business') || 'LeadLock';

  const handleLogout = () => {
    localStorage.removeItem('ll_token');
    localStorage.removeItem('ll_business');
    localStorage.removeItem('ll_is_admin');
    navigate('/login');
  };

  return (
    <div className="flex h-screen overflow-hidden bg-[#f8f9fb]">
      {/* Sidebar */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-[240px] flex flex-col bg-white border-r border-gray-200
        transform transition-transform duration-300 ease-in-out
        lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Logo */}
        <div className="flex items-center justify-between px-5 h-16 gradient-border-bottom">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl flex items-center justify-center bg-gradient-to-br from-indigo-500 to-violet-500 shadow-md shadow-indigo-500/20">
              <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
            </div>
            <span className="text-[15px] font-bold tracking-tight text-gray-900">
              Lead<span className="gradient-text">Lock</span>
            </span>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden text-gray-400 hover:text-gray-600 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Client name */}
        <div className="px-5 py-3.5 border-b border-gray-100">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400">Client</p>
          <p className="text-[13px] font-semibold truncate mt-1 text-gray-700">{businessName}</p>
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
                ${isActive ? 'bg-indigo-50/80 text-gray-900 nav-item-active' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'}
              `}
            >
              {({ isActive }) => (
                <>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${isActive ? 'bg-gradient-to-br from-indigo-500 to-indigo-600 shadow-sm shadow-indigo-500/20' : ''}`}>
                    <Icon className={`w-[18px] h-[18px] ${isActive ? 'text-white' : 'text-gray-400'}`} strokeWidth={isActive ? 2 : 1.5} />
                  </div>
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Compliance badge */}
        <div className="mx-3 mb-3 px-3 py-2.5 rounded-xl bg-gradient-to-r from-emerald-50 to-emerald-50/50 border border-emerald-100">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-md bg-emerald-500 flex items-center justify-center">
              <Shield className="w-3 h-3 text-white" />
            </div>
            <span className="text-[11px] font-semibold text-emerald-700">TCPA Compliant</span>
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
            Lead<span className="gradient-text">Lock</span>
          </span>
        </div>

        <div className="p-5 lg:p-8 max-w-[1200px] mx-auto bg-gradient-mesh min-h-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
