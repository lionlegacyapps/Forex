import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line,
} from 'recharts';
import { BarChart3, TrendingUp, DollarSign, Truck } from 'lucide-react';
import api from '../lib/api';
import { useTenantStore } from '../store/tenant';
import { formatCurrency } from '../lib/utils';
import type { Load, Driver } from '@truck-dispatch/shared';

const COLORS = ['#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#fb923c'];

export default function ReportsPage() {
  const { selectedTenant } = useTenantStore();
  const tenantQuery = selectedTenant ? `?tenantId=${selectedTenant.id}` : '';

  const { data: loadsData } = useQuery({
    queryKey: ['loads', selectedTenant?.id, 'all'],
    queryFn: async () => {
      const { data } = await api.get(`/loads?limit=200${selectedTenant ? `&tenantId=${selectedTenant.id}` : ''}`);
      return data.data as Load[];
    },
  });

  const { data: driversData } = useQuery({
    queryKey: ['drivers', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/drivers${selectedTenant ? `?tenantId=${selectedTenant.id}` : ''}`);
      return data.data as Driver[];
    },
  });

  const { data: chartData } = useQuery({
    queryKey: ['revenue-chart', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/dashboard/revenue-chart${tenantQuery}`);
      return data.data as { date: string; revenue: number; loads: number }[];
    },
  });

  const loads = loadsData || [];
  const drivers = driversData || [];

  // Equipment type breakdown
  const equipmentBreakdown = Object.entries(
    loads.reduce((acc: Record<string, number>, l) => {
      acc[l.equipmentType] = (acc[l.equipmentType] || 0) + 1;
      return acc;
    }, {})
  ).map(([name, value]) => ({ name: name.replace('_', ' '), value }));

  // Status breakdown
  const statusBreakdown = Object.entries(
    loads.reduce((acc: Record<string, number>, l) => {
      acc[l.status] = (acc[l.status] || 0) + 1;
      return acc;
    }, {})
  ).map(([name, value]) => ({ name: name.replace('_', ' '), value }));

  // Revenue by equipment type
  const revenueByEquipment = Object.entries(
    loads.filter((l) => l.status === 'DELIVERED').reduce((acc: Record<string, number>, l) => {
      acc[l.equipmentType] = (acc[l.equipmentType] || 0) + l.rate;
      return acc;
    }, {})
  ).map(([name, revenue]) => ({ name: name.replace('_', ' '), revenue }));

  // Top drivers by loads
  const driverPerformance = drivers.map((d) => ({
    name: d.name.split(' ')[0],
    loads: d.totalLoads,
    miles: Math.round(d.totalMiles / 1000),
    rating: d.rating,
  })).sort((a, b) => b.loads - a.loads).slice(0, 8);

  const totalRevenue = loads.filter((l) => l.status === 'DELIVERED').reduce((sum, l) => sum + l.rate, 0);
  const avgRate = loads.length ? loads.reduce((sum, l) => sum + l.rate, 0) / loads.length : 0;
  const deliveredLoads = loads.filter((l) => l.status === 'DELIVERED').length;
  const totalMiles = loads.filter((l) => l.miles).reduce((sum, l) => sum + (l.miles || 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Reports & Analytics</h1>
        <p className="text-sm text-muted-foreground">Performance metrics and revenue analysis</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { title: 'Total Revenue', value: formatCurrency(totalRevenue), icon: DollarSign, color: 'bg-amber-500/10 text-amber-400' },
          { title: 'Delivered Loads', value: deliveredLoads, icon: BarChart3, color: 'bg-green-500/10 text-green-400' },
          { title: 'Avg Rate/Load', value: formatCurrency(avgRate), icon: TrendingUp, color: 'bg-blue-500/10 text-blue-400' },
          { title: 'Total Miles', value: `${Math.round(totalMiles / 1000)}k mi`, icon: Truck, color: 'bg-purple-500/10 text-purple-400' },
        ].map(({ title, value, icon: Icon, color }) => (
          <div key={title} className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">{title}</p>
                <p className="text-2xl font-bold mt-1">{value}</p>
              </div>
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
                <Icon size={20} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Revenue over time */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold mb-4">Daily Revenue — Last 30 Days</h2>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(216 34% 20%)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(215 20% 55%)' }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fontSize: 10, fill: 'hsl(215 20% 55%)' }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
              <Tooltip
                contentStyle={{ background: 'hsl(222 47% 14%)', border: '1px solid hsl(216 34% 20%)', borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [formatCurrency(v), 'Revenue']}
              />
              <Bar dataKey="revenue" fill="hsl(212 95% 68%)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Equipment breakdown */}
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4">Loads by Equipment</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={equipmentBreakdown} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value">
                  {equipmentBreakdown.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: 'hsl(222 47% 14%)', border: '1px solid hsl(216 34% 20%)', borderRadius: 8, fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Status breakdown */}
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4">Load Status Distribution</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={statusBreakdown} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value">
                  {statusBreakdown.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: 'hsl(222 47% 14%)', border: '1px solid hsl(216 34% 20%)', borderRadius: 8, fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Revenue by equipment */}
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4">Revenue by Equipment</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={revenueByEquipment} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(216 34% 20%)" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 9, fill: 'hsl(215 20% 55%)' }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 9, fill: 'hsl(215 20% 55%)' }} width={60} />
                <Tooltip contentStyle={{ background: 'hsl(222 47% 14%)', border: '1px solid hsl(216 34% 20%)', borderRadius: 8, fontSize: 11 }}
                  formatter={(v: number) => [formatCurrency(v), 'Revenue']} />
                <Bar dataKey="revenue" fill="#34d399" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Driver performance */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold mb-4">Driver Performance</h2>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={driverPerformance}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(216 34% 20%)" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(215 20% 55%)' }} />
              <YAxis tick={{ fontSize: 10, fill: 'hsl(215 20% 55%)' }} />
              <Tooltip contentStyle={{ background: 'hsl(222 47% 14%)', border: '1px solid hsl(216 34% 20%)', borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="loads" name="Total Loads" fill="hsl(212 95% 68%)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
