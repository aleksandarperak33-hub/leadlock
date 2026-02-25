import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Zap, LogOut, Menu, X, ChevronLeft, ChevronRight } from 'lucide-react';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import ShortcutHelpModal from '../components/ShortcutHelpModal';

/**
 * BaseLayout - Shared sidebar layout for both dashboard and admin.
 *
 * @param {Object} props
 * @param {Array<{to: string, icon: Component, label: string}>} props.navItems - Navigation items
 * @param {string} [props.brandBadge] - Optional badge text next to brand (e.g. "ADMIN")
 * @param {string} props.userInitial - Single character for avatar
 * @param {string} props.userName - Display name below avatar
 * @param {string} [props.containerClass] - Extra class on root div (e.g. "admin-theme")
 * @param {React.ReactNode} [props.banners] - Banner elements rendered above Outlet
 * @param {Function} props.onLogout - Logout handler
 */
export default function BaseLayout({
  navItems,
  brandBadge,
  userInitial,
  userName,
  containerClass = '',
  banners,
  onLogout,
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { showHelp, setShowHelp, shortcuts } = useKeyboardShortcuts(navigate);

  const isActive = (path) =>
    location.pathname === path || location.pathname.startsWith(path + '/');

  const sidebarWidth = collapsed ? 'w-[72px]' : 'w-64';
  const contentMargin = collapsed ? 'lg:ml-[72px]' : 'lg:ml-64';

  return (
    <div className={`min-h-screen bg-[#F8F9FB] ${containerClass}`}>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex flex-col bg-white border-r border-gray-200/50 transition-all duration-300 ${sidebarWidth} ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-6">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center flex-shrink-0 shadow-sm">
            <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
          </div>
          {!collapsed && (
            <div className="flex items-center gap-2">
              <span className="text-[17px] font-bold text-gray-900 tracking-tight">
                LeadLock
              </span>
              {brandBadge && (
                <span className="text-[10px] font-bold bg-orange-50 text-orange-600 px-1.5 py-0.5 rounded-md uppercase tracking-wider ring-1 ring-inset ring-orange-500/10">
                  {brandBadge}
                </span>
              )}
            </div>
          )}
          <button
            onClick={() => setMobileOpen(false)}
            className="ml-auto lg:hidden text-gray-400 hover:text-gray-600 cursor-pointer"
            aria-label="Close menu"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-2 overflow-y-auto" role="navigation" aria-label="Main navigation">
          {navItems.map(({ to, icon: Icon, label }) => {
            const active = isActive(to);
            return (
              <div key={to} className="relative group">
                <button
                  onClick={() => {
                    navigate(to);
                    setMobileOpen(false);
                  }}
                  className={`flex items-center gap-3 mx-3 px-3 py-2 rounded-xl text-[13px] font-medium transition-all cursor-pointer w-[calc(100%-24px)] ${
                    active
                      ? 'text-gray-900 bg-gray-100/80'
                      : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                  }`}
                  aria-current={active ? 'page' : undefined}
                >
                  <Icon className={`w-[18px] h-[18px] flex-shrink-0 ${active ? 'text-orange-600' : ''}`} strokeWidth={active ? 2 : 1.75} />
                  {!collapsed && <span className="truncate">{label}</span>}
                </button>
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
        <div className="border-t border-gray-100">
          <div className="flex items-center gap-3 px-5 py-4">
            <div className="w-8 h-8 rounded-full bg-gray-100 text-gray-600 text-xs font-bold flex items-center justify-center flex-shrink-0">
              {userInitial}
            </div>
            {!collapsed && (
              <span className="text-sm font-medium text-gray-600 truncate">
                {userName}
              </span>
            )}
          </div>
          <div className="px-3 pb-2">
            <button
              onClick={onLogout}
              className="flex items-center gap-3 w-full px-3 py-2 rounded-xl text-[13px] font-medium text-gray-400 hover:text-red-500 hover:bg-red-50/50 transition-colors cursor-pointer"
            >
              <LogOut className="w-[18px] h-[18px] flex-shrink-0" />
              {!collapsed && <span>Sign out</span>}
            </button>
          </div>
          <button
            onClick={() => setCollapsed((prev) => !prev)}
            className="hidden lg:flex w-full justify-center py-3 text-gray-300 hover:text-gray-500 cursor-pointer transition-colors border-t border-gray-100"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
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
        <div className="lg:hidden flex items-center gap-3 px-4 h-14 sticky top-0 z-30 bg-white/90 backdrop-blur-sm border-b border-gray-200/50">
          <button
            onClick={() => setMobileOpen(true)}
            className="text-gray-500 cursor-pointer"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <span className="text-sm font-bold text-gray-900 tracking-tight">
            LeadLock{brandBadge ? ` ${brandBadge}` : ''}
          </span>
        </div>

        <div className="max-w-[1400px] mx-auto px-8 py-8 min-h-screen">
          {banners}
          <Outlet />
        </div>
      </div>

      {showHelp && (
        <ShortcutHelpModal
          shortcuts={shortcuts}
          onClose={() => setShowHelp(false)}
        />
      )}
    </div>
  );
}
