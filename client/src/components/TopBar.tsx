import { Bell, ChevronDown, LogOut, RefreshCw } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/auth';
import { useTenantStore } from '../store/tenant';
import api from '../lib/api';
import type { Tenant } from '@truck-dispatch/shared';
import { timeAgo } from '../lib/utils';

export default function TopBar() {
  const { user, logout } = useAuthStore();
  const { selectedTenant, setSelectedTenant, tenants, setTenants } = useTenantStore();
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [tenantOpen, setTenantOpen] = useState(false);
  const navigate = useNavigate();

  const isSuperDispatcher = user?.role === 'SUPER_DISPATCHER';

  useQuery({
    queryKey: ['tenants'],
    queryFn: async () => {
      const { data } = await api.get('/tenants');
      setTenants(data.data);
      if (!selectedTenant && data.data.length > 0 && !isSuperDispatcher) {
        setSelectedTenant(data.data[0]);
      }
      return data.data;
    },
    enabled: !!user,
  });

  const { data: alertsData } = useQuery({
    queryKey: ['alerts', 'unread'],
    queryFn: async () => {
      const { data } = await api.get('/alerts?unread=true');
      return data.data;
    },
    refetchInterval: 30000,
  });

  const alerts = alertsData || [];
  const unreadCount = alerts.length;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="h-16 border-b border-border bg-card px-6 flex items-center gap-4 flex-shrink-0">
      {/* Tenant selector */}
      <div className="relative">
        <button
          onClick={() => setTenantOpen(!tenantOpen)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 transition-colors text-sm"
        >
          <div className="w-2 h-2 rounded-full bg-green-400" />
          <span className="font-medium">
            {isSuperDispatcher
              ? selectedTenant ? selectedTenant.name : 'All Companies'
              : user?.tenant?.name || 'My Company'}
          </span>
          {isSuperDispatcher && <ChevronDown size={14} className="text-muted-foreground" />}
        </button>

        {tenantOpen && isSuperDispatcher && (
          <div className="absolute top-full left-0 mt-1 w-64 bg-card border border-border rounded-lg shadow-lg z-50">
            <div className="p-1">
              <button
                className="w-full text-left px-3 py-2 text-sm rounded hover:bg-secondary transition-colors"
                onClick={() => { setSelectedTenant(null); setTenantOpen(false); }}
              >
                <span className="font-medium">All Companies</span>
                <p className="text-xs text-muted-foreground">View all tenants</p>
              </button>
              {tenants.map((t: Tenant) => (
                <button
                  key={t.id}
                  className="w-full text-left px-3 py-2 text-sm rounded hover:bg-secondary transition-colors"
                  onClick={() => { setSelectedTenant(t); setTenantOpen(false); }}
                >
                  <span className="font-medium">{t.name}</span>
                  <p className="text-xs text-muted-foreground capitalize">{t.operationType?.toLowerCase()}</p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex-1" />

      {/* ELD Sync */}
      <button
        onClick={async () => { await api.post('/integrations/eld/sync'); }}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
        title="Sync ELD data"
      >
        <RefreshCw size={14} />
        <span className="hidden sm:inline">ELD Sync</span>
      </button>

      {/* Alerts */}
      <div className="relative">
        <button
          onClick={() => setAlertsOpen(!alertsOpen)}
          className="relative p-2 rounded-md hover:bg-secondary transition-colors"
        >
          <Bell size={18} className="text-muted-foreground" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-destructive text-[9px] font-bold flex items-center justify-center text-white">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        {alertsOpen && (
          <div className="absolute right-0 top-full mt-1 w-80 bg-card border border-border rounded-lg shadow-lg z-50">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <span className="text-sm font-semibold">Alerts</span>
              {unreadCount > 0 && (
                <span className="text-xs text-primary cursor-pointer" onClick={async () => {
                  await api.post('/alerts/read-all');
                  setAlertsOpen(false);
                }}>Mark all read</span>
              )}
            </div>
            <div className="max-h-72 overflow-y-auto">
              {alerts.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground text-center">No unread alerts</p>
              ) : (
                alerts.map((a: { id: string; type: string; title: string; message: string; createdAt: string }) => (
                  <div key={a.id} className="p-3 border-b border-border last:border-0 hover:bg-secondary/50 transition-colors">
                    <div className="flex items-start gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${a.type === 'WARNING' ? 'bg-amber-400' : a.type === 'ERROR' ? 'bg-red-400' : 'bg-blue-400'}`} />
                      <div>
                        <p className="text-xs font-semibold">{a.title}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{a.message}</p>
                        <p className="text-[10px] text-muted-foreground/60 mt-1">{timeAgo(a.createdAt)}</p>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Logout */}
      <button
        onClick={handleLogout}
        className="p-2 rounded-md hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground"
        title="Logout"
      >
        <LogOut size={18} />
      </button>
    </header>
  );
}
