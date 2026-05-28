import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Search, Filter, Package, X, ChevronDown } from 'lucide-react';
import api from '../lib/api';
import { useTenantStore } from '../store/tenant';
import { formatCurrency, getStatusColor, formatDate } from '../lib/utils';
import type { Load, Driver } from '@truck-dispatch/shared';

const EQUIPMENT_TYPES = ['DRY_VAN', 'REEFER', 'FLATBED', 'STEP_DECK', 'RGN', 'TANKER', 'INTERMODAL', 'HOTSHOT', 'POWER_ONLY'];
const STATUSES = ['AVAILABLE', 'ASSIGNED', 'IN_TRANSIT', 'AT_PICKUP', 'AT_DELIVERY', 'DELIVERED', 'CANCELLED'];

function CreateLoadModal({ tenants, drivers, onClose, onCreated }: {
  tenants: { id: string; name: string }[];
  drivers: Driver[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const { selectedTenant } = useTenantStore();
  const [form, setForm] = useState({
    tenantId: selectedTenant?.id || tenants[0]?.id || '',
    equipmentType: 'DRY_VAN',
    commodity: '',
    weight: '',
    miles: '',
    rate: '',
    driverPay: '',
    brokerName: '',
    brokerPhone: '',
    brokerMCNumber: '',
    referenceNumber: '',
    hazmat: false,
    teamLoad: false,
    specialInstructions: '',
    pickupCity: '',
    pickupState: '',
    pickupAddress: '',
    pickupDate: '',
    deliveryCity: '',
    deliveryState: '',
    deliveryAddress: '',
    deliveryDate: '',
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/loads', {
        tenantId: form.tenantId,
        equipmentType: form.equipmentType,
        commodity: form.commodity,
        weight: parseFloat(form.weight),
        miles: form.miles ? parseFloat(form.miles) : undefined,
        rate: parseFloat(form.rate),
        driverPay: form.driverPay ? parseFloat(form.driverPay) : undefined,
        brokerName: form.brokerName,
        brokerPhone: form.brokerPhone,
        brokerMCNumber: form.brokerMCNumber,
        referenceNumber: form.referenceNumber,
        hazmat: form.hazmat,
        teamLoad: form.teamLoad,
        specialInstructions: form.specialInstructions,
        stops: [
          {
            type: 'PICKUP',
            address: form.pickupAddress,
            city: form.pickupCity,
            state: form.pickupState,
            zip: '00000',
            scheduledArrival: form.pickupDate || new Date().toISOString(),
          },
          {
            type: 'DELIVERY',
            address: form.deliveryAddress,
            city: form.deliveryCity,
            state: form.deliveryState,
            zip: '00000',
            scheduledArrival: form.deliveryDate || new Date(Date.now() + 86400000).toISOString(),
          },
        ],
      });
      onCreated();
      onClose();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const F = ({ label, name, type = 'text', required = false }: { label: string; name: keyof typeof form; type?: string; required?: boolean }) => (
    <div>
      <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
      <input
        type={type}
        value={form[name] as string}
        onChange={(e) => setForm({ ...form, [name]: e.target.value })}
        required={required}
        className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
      />
    </div>
  );

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-card border border-border rounded-xl w-full max-w-2xl shadow-2xl my-4">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">New Load</h2>
          <button onClick={onClose}><X size={18} className="text-muted-foreground" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Tenant + Equipment */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Company</label>
              <select value={form.tenantId} onChange={(e) => setForm({ ...form, tenantId: e.target.value })}
                className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary">
                {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Equipment Type</label>
              <select value={form.equipmentType} onChange={(e) => setForm({ ...form, equipmentType: e.target.value })}
                className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary">
                {EQUIPMENT_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
              </select>
            </div>
          </div>

          {/* Pickup */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-green-400 uppercase tracking-wider">Pickup</p>
            <div className="grid grid-cols-3 gap-2">
              <F label="City" name="pickupCity" required />
              <F label="State" name="pickupState" required />
              <F label="Date/Time" name="pickupDate" type="datetime-local" />
            </div>
            <F label="Address" name="pickupAddress" />
          </div>

          {/* Delivery */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-red-400 uppercase tracking-wider">Delivery</p>
            <div className="grid grid-cols-3 gap-2">
              <F label="City" name="deliveryCity" required />
              <F label="State" name="deliveryState" required />
              <F label="Date/Time" name="deliveryDate" type="datetime-local" />
            </div>
            <F label="Address" name="deliveryAddress" />
          </div>

          {/* Load details */}
          <div className="grid grid-cols-3 gap-3">
            <F label="Commodity" name="commodity" required />
            <F label="Weight (lbs)" name="weight" type="number" required />
            <F label="Miles" name="miles" type="number" />
          </div>

          {/* Rates */}
          <div className="grid grid-cols-2 gap-3">
            <F label="Rate ($)" name="rate" type="number" required />
            <F label="Driver Pay ($)" name="driverPay" type="number" />
          </div>

          {/* Broker */}
          <div className="grid grid-cols-3 gap-3">
            <F label="Broker Name" name="brokerName" />
            <F label="Broker Phone" name="brokerPhone" />
            <F label="Broker MC#" name="brokerMCNumber" />
          </div>

          <F label="Reference Number" name="referenceNumber" />

          <div className="flex items-center gap-4 text-sm">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.hazmat} onChange={(e) => setForm({ ...form, hazmat: e.target.checked })} className="rounded" />
              <span>Hazmat</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.teamLoad} onChange={(e) => setForm({ ...form, teamLoad: e.target.checked })} className="rounded" />
              <span>Team Load</span>
            </label>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Special Instructions</label>
            <textarea value={form.specialInstructions} onChange={(e) => setForm({ ...form, specialInstructions: e.target.value })}
              rows={2} className="w-full px-2 py-1 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary resize-none" />
          </div>

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 h-9 rounded-lg border border-border text-sm hover:bg-secondary transition-colors">Cancel</button>
            <button type="submit" disabled={loading} className="flex-1 h-9 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50">
              {loading ? 'Creating...' : 'Create Load'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function LoadsPage() {
  const { selectedTenant } = useTenantStore();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  const tenantQuery = selectedTenant ? `&tenantId=${selectedTenant.id}` : '';

  const { data: loadsData } = useQuery({
    queryKey: ['loads', selectedTenant?.id, statusFilter],
    queryFn: async () => {
      const s = statusFilter ? `&status=${statusFilter}` : '';
      const { data } = await api.get(`/loads?limit=100${tenantQuery}${s}`);
      return data.data as Load[];
    },
    refetchInterval: 30000,
  });

  const { data: driversData } = useQuery({
    queryKey: ['drivers', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/drivers${selectedTenant ? `?tenantId=${selectedTenant.id}` : ''}`);
      return data.data as Driver[];
    },
  });

  const { data: tenantsData } = useQuery({
    queryKey: ['tenants'],
    queryFn: async () => {
      const { data } = await api.get('/tenants');
      return data.data as { id: string; name: string }[];
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/loads/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['loads'] }),
  });

  const loads = (loadsData || []).filter((l) =>
    search ? l.loadNumber.toLowerCase().includes(search.toLowerCase()) ||
      l.commodity.toLowerCase().includes(search.toLowerCase()) ||
      l.brokerName?.toLowerCase().includes(search.toLowerCase()) ||
      l.stops?.some((s) => s.city.toLowerCase().includes(search.toLowerCase()))
      : true
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Loads</h1>
          <p className="text-sm text-muted-foreground">{loads.length} loads</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus size={16} />
          New Load
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search loads, broker, city..."
            className="w-full h-9 pl-8 pr-3 rounded-lg border border-border bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 px-3 rounded-lg border border-border bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary">
          <option value="">All Statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>
      </div>

      {/* Loads table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-secondary/30">
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Load #</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Route</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Equipment</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Driver</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Status</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Rate</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Broker</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Created</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {loads.map((load) => {
              const pickup = load.stops?.[0];
              const delivery = load.stops?.find((s) => s.type === 'DELIVERY');
              return (
                <tr key={load.id} className="border-b border-border/50 last:border-0 hover:bg-secondary/20 transition-colors">
                  <td className="p-3">
                    <span className="font-mono text-sm text-primary font-bold">{load.loadNumber}</span>
                    {load.referenceNumber && <p className="text-xs text-muted-foreground">{load.referenceNumber}</p>}
                  </td>
                  <td className="p-3">
                    {pickup && delivery ? (
                      <div className="text-sm">
                        <p className="font-medium">{pickup.city}, {pickup.state}</p>
                        <p className="text-muted-foreground text-xs">→ {delivery.city}, {delivery.state}</p>
                        {load.miles && <p className="text-xs text-muted-foreground">{Math.round(load.miles)} mi</p>}
                      </div>
                    ) : '—'}
                  </td>
                  <td className="p-3 text-sm text-muted-foreground">{load.equipmentType.replace('_', ' ')}</td>
                  <td className="p-3">
                    {load.driver ? (
                      <span className="text-sm">{load.driver.name}</span>
                    ) : (
                      <span className="text-xs text-muted-foreground italic">Unassigned</span>
                    )}
                  </td>
                  <td className="p-3">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${getStatusColor(load.status)}`}>
                      {load.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="p-3">
                    <span className="text-sm font-semibold">{formatCurrency(load.rate)}</span>
                    {load.driverPay && <p className="text-xs text-muted-foreground">Pay: {formatCurrency(load.driverPay)}</p>}
                  </td>
                  <td className="p-3 text-sm text-muted-foreground">{load.brokerName || '—'}</td>
                  <td className="p-3 text-xs text-muted-foreground">{formatDate(load.createdAt)}</td>
                  <td className="p-3">
                    <button
                      onClick={() => { if (confirm('Cancel this load?')) deleteMutation.mutate(load.id); }}
                      className="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                    >
                      <X size={14} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {loads.length === 0 && (
          <div className="p-12 text-center">
            <Package size={32} className="text-muted-foreground mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">No loads found</p>
          </div>
        )}
      </div>

      {showCreate && (
        <CreateLoadModal
          tenants={tenantsData || []}
          drivers={driversData || []}
          onClose={() => setShowCreate(false)}
          onCreated={() => queryClient.invalidateQueries({ queryKey: ['loads'] })}
        />
      )}
    </div>
  );
}
