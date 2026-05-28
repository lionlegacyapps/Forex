import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import {
  Package, Truck, TrendingUp, CheckCircle, DollarSign,
  AlertTriangle, Navigation, RefreshCw, Layers,
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import api from '../lib/api';
import { useTenantStore } from '../store/tenant';
import { formatCurrency, getStatusColor, getStatusDot, hosColor, timeAgo } from '../lib/utils';
import type { DashboardStats, Driver, Load } from '@truck-dispatch/shared';

function StatCard({ title, value, icon: Icon, color, subtitle }: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  subtitle?: string;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold text-foreground mt-1">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
        </div>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { selectedTenant } = useTenantStore();
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<unknown>(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  const tenantQuery = selectedTenant ? `?tenantId=${selectedTenant.id}` : '';

  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboard-stats', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/dashboard/stats${tenantQuery}`);
      return data.data as DashboardStats;
    },
    refetchInterval: 30000,
  });

  const { data: mapData } = useQuery({
    queryKey: ['dashboard-map', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/dashboard/map-data${tenantQuery}`);
      return data.data as { drivers: Driver[]; loads: Load[] };
    },
    refetchInterval: 60000,
  });

  const { data: chartData } = useQuery({
    queryKey: ['revenue-chart', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/dashboard/revenue-chart${tenantQuery}`);
      return data.data as { date: string; revenue: number; loads: number }[];
    },
  });

  // Initialize Mapbox
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const mapboxToken = import.meta.env.VITE_MAPBOX_TOKEN;
    if (!mapboxToken || mapboxToken === 'your-mapbox-token') {
      setMapLoaded(false);
      return;
    }

    import('mapbox-gl').then((mapboxgl) => {
      mapboxgl.default.accessToken = mapboxToken;
      const map = new mapboxgl.default.Map({
        container: mapContainer.current!,
        style: 'mapbox://styles/mapbox/dark-v11',
        center: [-96, 38],
        zoom: 4,
      });

      map.on('load', () => {
        mapRef.current = map;
        setMapLoaded(true);
      });
    });

    return () => {
      if (mapRef.current) {
        (mapRef.current as { remove: () => void }).remove();
        mapRef.current = null;
      }
    };
  }, []);

  const stats = statsData;

  const statCards = [
    { title: 'Active Loads', value: stats?.activeLoads ?? '—', icon: Package, color: 'bg-blue-500/10 text-blue-400', subtitle: `${stats?.inTransitLoads ?? 0} in transit` },
    { title: 'Available Drivers', value: stats?.availableDrivers ?? '—', icon: Truck, color: 'bg-green-500/10 text-green-400', subtitle: 'Ready to dispatch' },
    { title: 'Delivered Today', value: stats?.deliveredToday ?? '—', icon: CheckCircle, color: 'bg-emerald-500/10 text-emerald-400', subtitle: `${stats?.onTimeDeliveryRate ?? 0}% on-time rate` },
    { title: 'Revenue Today', value: stats ? formatCurrency(stats.revenueToday) : '—', icon: DollarSign, color: 'bg-amber-500/10 text-amber-400', subtitle: `${formatCurrency(stats?.revenueWeek ?? 0)} this week` },
    { title: 'Monthly Revenue', value: stats ? formatCurrency(stats.revenueMonth) : '—', icon: TrendingUp, color: 'bg-purple-500/10 text-purple-400', subtitle: `${stats ? formatCurrency(stats.avgRatePerMile) : '—'}/mile avg` },
  ];

  const drivers = mapData?.drivers || [];
  const activeLoads = mapData?.loads || [];
  const alerts = stats?.alerts || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {selectedTenant ? selectedTenant.name : 'All Companies'} — Live Overview
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <div className="w-2 h-2 rounded-full bg-green-400 pulse-dot" />
          Live • Refreshes every 30s
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {statCards.map((s) => (
          <StatCard key={s.title} {...s} />
        ))}
      </div>

      {/* Map + Alerts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Live Map */}
        <div className="lg:col-span-2 bg-card border border-border rounded-xl overflow-hidden">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Navigation size={16} className="text-primary" />
              <h2 className="text-sm font-semibold">Live Fleet Map</h2>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-green-400" />Available ({drivers.filter((d) => d.status === 'AVAILABLE').length})</span>
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-400" />Driving ({drivers.filter((d) => d.status === 'DRIVING').length})</span>
            </div>
          </div>

          <div className="h-80 relative">
            {/* Map container */}
            <div ref={mapContainer} className="absolute inset-0" />

            {/* Fallback map when no Mapbox token */}
            {!mapLoaded && (
              <div className="absolute inset-0 bg-slate-900 flex flex-col items-center justify-center">
                <div className="relative w-full h-full overflow-hidden">
                  {/* US Map SVG placeholder */}
                  <svg viewBox="0 0 800 450" className="w-full h-full opacity-20">
                    <rect width="800" height="450" fill="#1a2332" />
                    {/* Simple US outline */}
                    <path d="M150,80 L680,80 L720,180 L700,320 L560,380 L400,390 L200,350 L100,280 L90,180 Z" fill="none" stroke="#4b6584" strokeWidth="2" />
                    <path d="M200,220 L300,200 L400,210 L500,195 L600,215 L650,240 L580,300 L460,320 L350,330 L250,310 L180,280 Z" fill="#1e2d40" stroke="#2d4a6b" strokeWidth="1" />
                  </svg>

                  {/* Driver dots */}
                  {drivers.slice(0, 8).map((driver, i) => {
                    const positions = [
                      { x: '40%', y: '55%' }, { x: '15%', y: '50%' }, { x: '75%', y: '60%' },
                      { x: '35%', y: '65%' }, { x: '82%', y: '72%' }, { x: '50%', y: '45%' },
                      { x: '62%', y: '35%' }, { x: '25%', y: '68%' },
                    ];
                    const pos = positions[i] || { x: `${30 + i * 8}%`, y: '55%' };
                    const color = driver.status === 'AVAILABLE' ? '#4ade80' : driver.status === 'DRIVING' ? '#fbbf24' : '#94a3b8';
                    return (
                      <div
                        key={driver.id}
                        className="absolute transform -translate-x-1/2 -translate-y-1/2"
                        style={{ left: pos.x, top: pos.y }}
                        title={`${driver.name} — ${driver.status}`}
                      >
                        <div className="relative">
                          <div className="w-4 h-4 rounded-full border-2 border-background flex items-center justify-center" style={{ backgroundColor: color }}>
                            <Truck size={8} className="text-background" />
                          </div>
                          <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-[9px] text-white/70 font-medium">
                            {driver.truckNumber || driver.name.split(' ')[0]}
                          </div>
                        </div>
                      </div>
                    );
                  })}

                  <div className="absolute bottom-4 left-4 text-xs text-slate-400 bg-slate-800/80 px-2 py-1 rounded">
                    Add VITE_MAPBOX_TOKEN for live map
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Alerts */}
        <div className="bg-card border border-border rounded-xl flex flex-col">
          <div className="p-4 border-b border-border flex items-center gap-2">
            <AlertTriangle size={16} className="text-amber-400" />
            <h2 className="text-sm font-semibold">Active Alerts</h2>
            {alerts.length > 0 && (
              <span className="ml-auto text-xs bg-amber-400/10 text-amber-400 px-2 py-0.5 rounded-full">{alerts.length}</span>
            )}
          </div>
          <div className="flex-1 overflow-y-auto">
            {alerts.length === 0 ? (
              <div className="p-6 text-center">
                <CheckCircle size={24} className="text-green-400 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">All clear — no active alerts</p>
              </div>
            ) : (
              alerts.map((alert) => (
                <div key={alert.id} className="p-3 border-b border-border/50 last:border-0 hover:bg-secondary/30 transition-colors">
                  <div className="flex items-start gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${alert.type === 'WARNING' ? 'bg-amber-400' : alert.type === 'ERROR' ? 'bg-red-400' : 'bg-blue-400'}`} />
                    <div className="flex-1">
                      <p className="text-xs font-semibold">{alert.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{alert.message}</p>
                      <p className="text-[10px] text-muted-foreground/60 mt-1">{timeAgo(alert.createdAt)}</p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Revenue chart + Active loads */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Revenue Chart */}
        <div className="lg:col-span-2 bg-card border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold">Revenue — Last 30 Days</h2>
            <span className="text-xs text-muted-foreground">{formatCurrency(stats?.revenueMonth ?? 0)} total</span>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData || []}>
                <defs>
                  <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="hsl(212 95% 68%)" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="hsl(212 95% 68%)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(216 34% 20%)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(215 20% 55%)' }} tickFormatter={(v) => v.slice(5)} />
                <YAxis tick={{ fontSize: 10, fill: 'hsl(215 20% 55%)' }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ background: 'hsl(222 47% 14%)', border: '1px solid hsl(216 34% 20%)', borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [formatCurrency(v), 'Revenue']}
                />
                <Area type="monotone" dataKey="revenue" stroke="hsl(212 95% 68%)" fill="url(#revenueGrad)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Active Loads */}
        <div className="bg-card border border-border rounded-xl flex flex-col">
          <div className="p-4 border-b border-border flex items-center gap-2">
            <Layers size={16} className="text-primary" />
            <h2 className="text-sm font-semibold">Active Loads</h2>
          </div>
          <div className="flex-1 overflow-y-auto">
            {activeLoads.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground text-center">No active loads</p>
            ) : (
              activeLoads.map((load) => {
                const pickup = (load.stops as { type: string; city: string; state: string }[])?.[0];
                const delivery = (load.stops as { type: string; city: string; state: string }[])?.find((s) => s.type === 'DELIVERY');
                return (
                  <div key={load.id} className="p-3 border-b border-border/50 last:border-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold font-mono">{load.loadNumber}</span>
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${getStatusColor(load.status)}`}>
                        {load.status.replace('_', ' ')}
                      </span>
                    </div>
                    {pickup && delivery && (
                      <p className="text-xs text-muted-foreground">
                        {pickup.city}, {pickup.state} → {delivery.city}, {delivery.state}
                      </p>
                    )}
                    {load.driver && (
                      <div className="flex items-center gap-1.5 mt-1">
                        <div className={`w-1.5 h-1.5 rounded-full ${getStatusDot(load.driver.status || '')}`} />
                        <span className="text-[11px] text-muted-foreground">{(load.driver as { name: string }).name}</span>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Driver HOS Overview */}
      <div className="bg-card border border-border rounded-xl">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Truck size={16} className="text-primary" />
            Driver HOS & Status
          </h2>
          <span className="text-xs text-muted-foreground">{drivers.length} drivers tracked</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Driver</th>
                <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Status</th>
                <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Location</th>
                <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Drive Remaining</th>
                <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Shift Remaining</th>
                <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Cycle Remaining</th>
              </tr>
            </thead>
            <tbody>
              {drivers.slice(0, 10).map((driver) => (
                <tr key={driver.id} className="border-b border-border/50 last:border-0 hover:bg-secondary/20 transition-colors">
                  <td className="p-3">
                    <div>
                      <p className="text-sm font-medium">{driver.name}</p>
                      <p className="text-xs text-muted-foreground">{(driver as { truckNumber?: string }).truckNumber || 'No truck'}</p>
                    </div>
                  </td>
                  <td className="p-3">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${getStatusColor(driver.status)}`}>
                      {driver.status}
                    </span>
                  </td>
                  <td className="p-3 text-xs text-muted-foreground">
                    {driver.currentCity && driver.currentState
                      ? `${driver.currentCity}, ${driver.currentState}`
                      : '—'}
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-semibold tabular-nums ${hosColor(driver.hosDriveRemaining)}`}>
                        {driver.hosDriveRemaining.toFixed(1)}h
                      </span>
                      <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${driver.hosDriveRemaining >= 6 ? 'bg-green-400' : driver.hosDriveRemaining >= 3 ? 'bg-amber-400' : 'bg-red-400'}`}
                          style={{ width: `${(driver.hosDriveRemaining / 11) * 100}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="p-3 text-sm text-muted-foreground tabular-nums">{driver.hosShiftRemaining.toFixed(1)}h</td>
                  <td className="p-3 text-sm text-muted-foreground tabular-nums">{driver.hosCycleRemaining.toFixed(1)}h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
