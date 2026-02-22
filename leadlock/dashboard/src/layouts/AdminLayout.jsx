import {
  Zap, LayoutDashboard, Building2, Users, DollarSign,
  Send, Rocket, Megaphone, Mail, Lightbulb, FileText,
  Factory, MessageSquare, BarChart2, Bot,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import BaseLayout from './BaseLayout';

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
  { to: '/content-factory', icon: Factory, label: 'Content Factory' },
  { to: '/channel-scripts', icon: MessageSquare, label: 'Channel Scripts' },
  { to: '/analytics', icon: BarChart2, label: 'Analytics' },
  { to: '/agents', icon: Bot, label: 'Agent Army' },
];

export default function AdminLayout() {
  const { logout } = useAuth();

  return (
    <BaseLayout
      navItems={NAV_ITEMS}
      brandBadge="ADMIN"
      userInitial="A"
      userName="Admin"
      containerClass="admin-theme"
      onLogout={logout}
    />
  );
}
