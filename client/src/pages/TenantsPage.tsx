import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Building2, Truck, Package, Users, X, Edit2, Check } from 'lucide-react';
import api from '../lib/api';
import type { Tenant } from '@truck-dispatch/shared';
import { formatDate } from '../lib/utils';

const OPERATION_TYPES = ['LOCAL', 'REGIONAL', 'LONGHAUL', 'MIXED'];

function TenantModal({ tenant, onClose, onSaved }: {
  tenant?: Tenant;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: tenant?.name || '',
    dotNumber: tenant?.dotNumber || '',
    mcNumber: tenant?.mcNumber || '',
    address: tenant?.address || '',
    phone: tenant?.phone || '',
    email: tenant?.email || '',
    operationType: tenant?.operationType || 'MIXED',
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (tenant) {
        await api.put(`/tenants/${tenant.id}`, form);
      } else {
        await api.post('/tenants', form);
      }
      onSaved();
      onClose();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const F = ({ label, key, type = 'text' }: { label: string; key: keyof typeof form; type?: string }) => (
    <div>
      <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
      <input type={type} value={form[key] as string}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
    </div>
  );

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-md shadow-2xl">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">{tenant ? 'Edit Company' : 'Add Company'}</h2>
          <button onClick={onClose}><X size={18} className="text-muted-foreground" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-3">
          <F label="Company Name" key="name" />
          <div className="grid grid-cols-2 gap-3">
            <F label="DOT Number" key="dotNumber" />
            <F label="MC Number" key="mcNumber" />
          </div>
          <F label="Address" key="address" />
          <div className="grid grid-cols-2 gap-3">
            <F label="Phone" key="phone" />
            <F label="Email" key="email" type="email" />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Operation Type</label>
            <select value={form.operationType} onChange={(e) => setForm({ ...form, operationType: e.target.value as Tenant['operationType'] })}
              className="w-full h-8 px-2 rounded border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary">
              {OPERATION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 h-9 rounded-lg border border-border text-sm hover:bg-secondary transition-colors">Cancel</button>
            <button type="submit" disabled={loading} className="flex-1 h-9 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50">
              {loading ? 'Saving...' : tenant ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function TenantsPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<Tenant | null>(null);

  const { data: tenantsData } = useQuery({
    queryKey: ['tenants'],
    queryFn: async () => {
      const { data } = await api.get('/tenants');
      return data.data as (Tenant & { _count: { drivers: number; loads: number; users: number } })[];
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/tenants/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tenants'] }),
  });

  const operationColors: Record<string, string> = {
    LOCAL: 'text-green-400 bg-green-400/10',
    REGIONAL: 'text-blue-400 bg-blue-400/10',
    LONGHAUL: 'text-amber-400 bg-amber-400/10',
    MIXED: 'text-purple-400 bg-purple-400/10',
  };

  const tenants = tenantsData || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Companies</h1>
          <p className="text-sm text-muted-foreground">{tenants.length} tenant companies</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus size={16} />
          Add Company
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {tenants.map((tenant) => (
          <div key={tenant.id} className={`bg-card border rounded-xl p-5 ${!tenant.isActive ? 'opacity-60' : 'border-border hover:border-primary/20'} transition-colors`}>
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                  <Building2 size={18} className="text-primary" />
                </div>
                <div>
                  <p className="font-semibold">{tenant.name}</p>
                  {!tenant.isActive && <p className="text-xs text-red-400">Inactive</p>}
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => setEditing(tenant)}
                  className="p-1.5 rounded hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground">
                  <Edit2 size={14} />
                </button>
                <button onClick={() => { if (confirm('Deactivate this company?')) deactivateMutation.mutate(tenant.id); }}
                  className="p-1.5 rounded hover:bg-destructive/10 hover:text-destructive transition-colors text-muted-foreground">
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2 mb-3">
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${operationColors[tenant.operationType] || 'text-muted-foreground bg-secondary'}`}>
                {tenant.operationType}
              </span>
              {tenant.dotNumber && <span className="text-xs text-muted-foreground">DOT: {tenant.dotNumber}</span>}
            </div>

            {tenant.address && <p className="text-xs text-muted-foreground mb-3">📍 {tenant.address}</p>}
            {tenant.phone && <p className="text-xs text-muted-foreground mb-1">📞 {tenant.phone}</p>}

            <div className="grid grid-cols-3 gap-2 mt-4 pt-4 border-t border-border/50">
              {[
                { icon: Truck, label: 'Drivers', count: tenant._count?.drivers || 0 },
                { icon: Package, label: 'Loads', count: tenant._count?.loads || 0 },
                { icon: Users, label: 'Users', count: tenant._count?.users || 0 },
              ].map(({ icon: Icon, label, count }) => (
                <div key={label} className="text-center">
                  <Icon size={14} className="text-muted-foreground mx-auto mb-0.5" />
                  <p className="text-lg font-bold">{count}</p>
                  <p className="text-[10px] text-muted-foreground">{label}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {tenants.length === 0 && (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <Building2 size={32} className="text-muted-foreground mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">No companies yet. Add your first tenant company.</p>
        </div>
      )}

      {showCreate && (
        <TenantModal
          onClose={() => setShowCreate(false)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ['tenants'] })}
        />
      )}
      {editing && (
        <TenantModal
          tenant={editing}
          onClose={() => setEditing(null)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ['tenants'] })}
        />
      )}
    </div>
  );
}
