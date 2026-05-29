import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Truck, Package, Users, Brain, FileText,
  BarChart3, Building2, Settings, Layers, ExternalLink, Zap,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { useAuthStore } from '../store/auth';

const navItems = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/dispatch', icon: Layers, label: 'Dispatch Board' },
  { path: '/loads', icon: Package, label: 'Loads' },
  { path: '/drivers', icon: Truck, label: 'Drivers' },
  { path: '/loadboard', icon: ExternalLink, label: 'Load Board' },
  { path: '/ai-assistant', icon: Brain, label: 'AI Assistant', badge: 'AI' },
  { path: '/documents', icon: FileText, label: 'Documents' },
  { path: '/reports', icon: BarChart3, label: 'Reports' },
];

const adminItems = [
  { path: '/tenants', icon: Building2, label: 'Companies' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

export default function Sidebar() {
  const { user } = useAuthStore();
  const isSuperDispatcher = user?.role === 'SUPER_DISPATCHER';

  return (
    <aside className="w-64 flex-shrink-0 bg-card border-r border-border flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <Truck size={16} className="text-primary-foreground" />
          </div>
          <div>
            <p className="text-sm font-bold text-foreground leading-none">TruckDispatch</p>
            <p className="text-xs text-muted-foreground mt-0.5">AI Platform</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-3">
        <div className="space-y-1">
          {navItems.map(({ path, icon: Icon, label, badge }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
                )
              }
            >
              <Icon size={16} />
              <span className="flex-1">{label}</span>
              {badge && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-primary/20 text-primary">
                  {badge}
                </span>
              )}
            </NavLink>
          ))}
        </div>

        {isSuperDispatcher && (
          <>
            <div className="my-4 border-t border-border" />
            <p className="px-3 mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Admin</p>
            <div className="space-y-1">
              {adminItems.map(({ path, icon: Icon, label }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary/10 text-primary'
                        : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
                    )
                  }
                >
                  <Icon size={16} />
                  {label}
                </NavLink>
              ))}
            </div>
          </>
        )}
      </nav>

      {/* User info */}
      <div className="p-3 border-t border-border">
        <div className="flex items-center gap-3 px-3 py-2 rounded-md bg-secondary/50">
          <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
            <span className="text-xs font-bold text-primary">
              {user?.name?.split(' ').map((n) => n[0]).join('').slice(0, 2)}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-foreground truncate">{user?.name}</p>
            <p className="text-xs text-muted-foreground capitalize truncate">
              {user?.role?.toLowerCase().replace('_', ' ')}
            </p>
          </div>
          <Zap size={12} className="text-primary flex-shrink-0" />
        </div>
      </div>
    </aside>
  );
}
