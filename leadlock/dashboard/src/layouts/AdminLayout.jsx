import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  Zap, LayoutDashboard, Building2, Users, DollarSign,
  Send, Rocket, Megaphone, Mail, Lightbulb, FileText,
  LogOut, Menu, X, ChevronLeft, ChevronRight,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/dashboard', icon: Zap, label: 'Command Center' },
  { to: '/overview', icon: LayoutDashboard, label: 'Overview' },
  { to: '/clients', icon: Building2, label: 'Clients' },
  { to: '/leads', icon: Users, label: 'All Leads' },
  { to: '/revenue', icon: DollarSign, label: 'Revenue' },
  { to: '/outreach', icon: Send, label: 'Outreach' },
  { to: '/sales-engine', icon: Rocket, label: 'Sales Engine' },
  { to: '/campaigns', icon: Megaphone, label: 'Campaigns' },
  { to: '/inbox', icon: Mail, label: 'Inbox' },
  { to: '/insights', icon: Lightbulb, label: 'Insights' },
  { to: '/templates', icon: FileText, label: 'Templates' },
];

export default function AdminLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem('ll_token');
    localStorage.removeItem('ll_business');
    localStorage.removeItem('ll_is_admin');
    localStorage.removeItem('ll_client_id');
    window.location.href = '/login';
  };

  const isActive = (path) => location.pathname === path || location.pathname.startsWith(path + '/');

  const sidebarWidth = collapsed ? 'w-[72px]' : 'w-64';
  const contentMargin = collapsed ? 'lg:ml-[72px]' : 'lg:ml-64';

  return (
    <div className="admin-theme min-h-screen bg-[#FAFAFA]">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex flex-col bg-white border-r border-gray-200/60 transition-all duration-300 ${sidebarWidth} ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-6">
          <div className="w-9 h-9 rounded-xl bg-orange-500 flex items-center justify-center flex-shrink-0">
            <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
          </div>
          {!collapsed && (
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-gray-900">
                LeadLock
              </span>
              <span className="text-[10px] font-bold bg-orange-100 text-orange-600 px-1.5 py-0.5 rounded-md uppercase tracking-wider">
                ADMIN
              </span>
            </div>
          )}
          {/* Mobile close */}
          <button
            onClick={() => setMobileOpen(false)}
            className="ml-auto lg:hidden text-gray-400 hover:text-gray-600 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-2 overflow-y-auto">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
            const active = isActive(to);

            return (
              <div key={to} className="relative group">
                <button
                  onClick={() => {
                    navigate(to);
                    setMobileOpen(false);
                  }}
                  className={`flex items-center gap-3 mx-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors cursor-pointer w-[calc(100%-24px)] ${
                    active
                      ? 'text-orange-600 bg-orange-50/80 border-l-2 border-orange-500'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <Icon className={`w-5 h-5 flex-shrink-0 ${active ? 'text-orange-600' : ''}`} />
                  {!collapsed && <span className="truncate">{label}</span>}
                </button>
                {/* Tooltip when collapsed */}
                {collapsed && (
                  <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2 py-1 bg-gray-900 text-white text-xs rounded-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50 hidden lg:block">
                    {label}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Bottom section */}
        <div className="border-t border-gray-200/60">
          {/* Admin user info */}
          <div className="flex items-center gap-3 px-5 py-4">
            <div className="w-8 h-8 rounded-full bg-orange-100 text-orange-600 text-xs font-bold flex items-center justify-center flex-shrink-0">
              A
            </div>
            {!collapsed && (
              <span className="text-sm font-medium text-gray-700 truncate">
                Admin
              </span>
            )}
          </div>

          {/* Sign out */}
          <div className="px-3 pb-2">
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 w-full px-3 py-2 rounded-xl text-sm font-medium text-gray-400 hover:text-red-500 hover:bg-gray-50 transition-colors cursor-pointer"
            >
              <LogOut className="w-5 h-5 flex-shrink-0" />
              {!collapsed && <span>Sign out</span>}
            </button>
          </div>

          {/* Collapse toggle */}
          <button
            onClick={() => setCollapsed((prev) => !prev)}
            className="hidden lg:flex w-full justify-center py-3 text-gray-400 hover:text-gray-600 cursor-pointer transition-colors border-t border-gray-200/60"
          >
            {collapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className={`transition-all duration-300 ${contentMargin}`}>
        {/* Mobile header */}
        <div className="lg:hidden flex items-center gap-3 px-4 h-14 sticky top-0 z-30 bg-white/90 backdrop-blur-sm border-b border-gray-200/60">
          <button
            onClick={() => setMobileOpen(true)}
            className="text-gray-500 cursor-pointer"
          >
            <Menu className="w-5 h-5" />
          </button>
          <span className="text-sm font-semibold text-gray-900">
            LeadLock Admin
          </span>
        </div>

        <div className="max-w-[1400px] mx-auto px-8 py-8 min-h-screen">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
