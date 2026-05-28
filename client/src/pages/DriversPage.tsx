import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Search, Truck, Star, Phone, X } from 'lucide-react';
import api from '../lib/api';
import { useTenantStore } from '../store/tenant';
import { getStatusColor, hosColor, formatMiles } from '../lib/utils';
import type { Driver } from '@truck-dispatch/shared';

const EQUIPMENT_TYPES = ['DRY_VAN', 'REEFER', 'FLATBED', 'STEP_DECK', 'RGN', 'TANKER', 'INTERMODAL', 'HOTSHOT', 'POWER_ONLY'];
const ELD_PROVIDERS = ['MOTIVE', 'SAMSARA', 'GEOTAB', 'NONE'];

function CreateDriverModal({ tenants, onClose, onCreated }: {
  tenants: { id: string; name: string }[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const { selectedTenant } = useTenantStore();
  const [form, setForm] = useState({
    tenantId: selectedTenant?.id || tenants[0]?.id || '',
    name: '', email: '', phone: '',
    cdlNumber: '', cdlState: '', cdlClass: 'A', cdlExpiry: '',
    truckNumber: '', trailerNumber: '',
    eldProvider: 'NONE', eldDriverId: '',
    equipmentType: ['DRY_VAN'] as string[],
  });
  const [loading, setLoading] = useState(false);

  const toggleEquipment = (type: string) => {
    setForm((f) => ({
      ...f,
      equipmentType: f.equipmentType.includes(type)
        ? f.equipmentType.filter((e) => e !== type)
        : [...f.equipmentType, type],
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/drivers', form);
      onCreated();
      onClose();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-card border border-border rounded-xl w-full max-w-xl shadow-2xl my-4">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">Add Driver</h2>
          <button onClick={onClose}><X size={18} className="text-muted-foreground" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Company</label>
            <select value={form.tenantId} onChange={(e) => setForm({ ...form, tenantId: e.target.value })}
              className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary">
              {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Full Name', key: 'name', required: true },
              { label: 'Phone', key: 'phone', required: true },
              { label: 'Email', key: 'email' },
              { label: 'Truck Number', key: 'truckNumber' },
            ].map(({ label, key, required }) => (
              <div key={key}>
                <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
                <input type="text" value={(form as Record<string, unknown>)[key] as string}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  required={required}
                  className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
              </div>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">CDL Number</label>
              <input type="text" value={form.cdlNumber} onChange={(e) => setForm({ ...form, cdlNumber: e.target.value })}
                required className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">CDL State</label>
              <input type="text" value={form.cdlState} onChange={(e) => setForm({ ...form, cdlState: e.target.value })}
                maxLength={2} required className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">CDL Expiry</label>
              <input type="date" value={form.cdlExpiry} onChange={(e) => setForm({ ...form, cdlExpiry: e.target.value })}
                required className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-2">Equipment Types</label>
            <div className="flex flex-wrap gap-2">
              {EQUIPMENT_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => toggleEquipment(type)}
                  className={`text-xs px-2 py-1 rounded border transition-colors ${
                    form.equipmentType.includes(type)
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:border-border/60'
                  }`}
                >
                  {type.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">ELD Provider</label>
              <select value={form.eldProvider} onChange={(e) => setForm({ ...form, eldProvider: e.target.value })}
                className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary">
                {ELD_PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">ELD Driver ID</label>
              <input type="text" value={form.eldDriverId} onChange={(e) => setForm({ ...form, eldDriverId: e.target.value })}
                className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 h-9 rounded-lg border border-border text-sm hover:bg-secondary transition-colors">Cancel</button>
            <button type="submit" disabled={loading} className="flex-1 h-9 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50">
              {loading ? 'Adding...' : 'Add Driver'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function DriversPage() {
  const { selectedTenant } = useTenantStore();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  const { data: driversData } = useQuery({
    queryKey: ['drivers', selectedTenant?.id, statusFilter],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (selectedTenant) params.set('tenantId', selectedTenant.id);
      if (statusFilter) params.set('status', statusFilter);
      const { data } = await api.get(`/drivers?${params}`);
      return data.data as Driver[];
    },
    refetchInterval: 30000,
  });

  const { data: tenantsData } = useQuery({
    queryKey: ['tenants'],
    queryFn: async () => {
      const { data } = await api.get('/tenants');
      return data.data as { id: string; name: string }[];
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/drivers/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['drivers'] }),
  });

  const drivers = (driversData || []).filter((d) =>
    search ? d.name.toLowerCase().includes(search.toLowerCase()) ||
      d.phone.includes(search) ||
      d.truckNumber?.toLowerCase().includes(search.toLowerCase()) ||
      d.currentCity?.toLowerCase().includes(search.toLowerCase())
      : true
  );

  const statusCounts = {
    AVAILABLE: drivers.filter((d) => d.status === 'AVAILABLE').length,
    DRIVING: drivers.filter((d) => d.status === 'DRIVING').length,
    ON_DUTY: drivers.filter((d) => d.status === 'ON_DUTY').length,
    OFF_DUTY: drivers.filter((d) => d.status === 'OFF_DUTY').length,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Drivers</h1>
          <p className="text-sm text-muted-foreground">{drivers.length} drivers</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus size={16} />
          Add Driver
        </button>
      </div>

      {/* Status Summary */}
      <div className="grid grid-cols-4 gap-3">
        {Object.entries(statusCounts).map(([status, count]) => (
          <button
            key={status}
            onClick={() => setStatusFilter(statusFilter === status ? '' : status)}
            className={`p-3 rounded-xl border text-left transition-colors ${statusFilter === status ? 'border-primary bg-primary/10' : 'bg-card border-border hover:border-border/60'}`}
          >
            <p className="text-xl font-bold">{count}</p>
            <p className="text-xs text-muted-foreground">{status.replace('_', ' ')}</p>
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, phone, truck..."
          className="w-full h-9 pl-8 pr-3 rounded-lg border border-border bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
      </div>

      {/* Drivers grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {drivers.map((driver) => (
          <div key={driver.id} className="bg-card border border-border rounded-xl p-4 hover:border-primary/20 transition-colors">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <span className="text-sm font-bold text-primary">{driver.name.split(' ').map((n) => n[0]).join('')}</span>
                </div>
                <div>
                  <p className="text-sm font-semibold">{driver.name}</p>
                  <p className="text-xs text-muted-foreground">{driver.truckNumber || 'No truck assigned'}</p>
                </div>
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${getStatusColor(driver.status)}`}>
                {driver.status}
              </span>
            </div>

            {driver.currentCity && (
              <p className="text-xs text-muted-foreground mb-3">📍 {driver.currentCity}, {driver.currentState}</p>
            )}

            {/* HOS bars */}
            <div className="space-y-1.5 mb-3">
              {[
                { label: 'Drive', value: driver.hosDriveRemaining, max: 11 },
                { label: 'Shift', value: driver.hosShiftRemaining, max: 14 },
                { label: 'Cycle', value: driver.hosCycleRemaining, max: 70 },
              ].map(({ label, value, max }) => (
                <div key={label} className="flex items-center gap-2">
                  <span className="text-[10px] text-muted-foreground w-8">{label}</span>
                  <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${value / max >= 0.5 ? 'bg-green-400' : value / max >= 0.25 ? 'bg-amber-400' : 'bg-red-400'}`}
                      style={{ width: `${(value / max) * 100}%` }}
                    />
                  </div>
                  <span className={`text-[10px] tabular-nums w-8 text-right ${hosColor(value)}`}>{value.toFixed(1)}h</span>
                </div>
              ))}
            </div>

            {/* Equipment */}
            <div className="flex flex-wrap gap-1 mb-3">
              {(Array.isArray(driver.equipmentType) ? driver.equipmentType : [driver.equipmentType]).map((t) => (
                <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">{t}</span>
              ))}
            </div>

            <div className="flex items-center justify-between text-xs text-muted-foreground border-t border-border/50 pt-3">
              <div className="flex items-center gap-1">
                <Star size={10} className="text-amber-400" />
                <span>{driver.rating.toFixed(1)}</span>
                <span className="mx-1">•</span>
                <span>{driver.totalLoads} loads</span>
              </div>
              <div className="flex items-center gap-2">
                {driver.eldProvider && driver.eldProvider !== 'NONE' && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-400/10 text-blue-400">{driver.eldProvider}</span>
                )}
                <button onClick={() => {}} className="p-1 rounded hover:bg-secondary transition-colors"><Phone size={12} /></button>
                <button onClick={() => { if (confirm('Deactivate driver?')) deleteMutation.mutate(driver.id); }}
                  className="p-1 rounded hover:bg-destructive/10 hover:text-destructive transition-colors text-muted-foreground">
                  <X size={12} />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {drivers.length === 0 && (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <Truck size={32} className="text-muted-foreground mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">No drivers found</p>
        </div>
      )}

      {showCreate && (
        <CreateDriverModal
          tenants={tenantsData || []}
          onClose={() => setShowCreate(false)}
          onCreated={() => queryClient.invalidateQueries({ queryKey: ['drivers'] })}
        />
      )}
    </div>
  );
}
