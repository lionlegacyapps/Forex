import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Tenant } from '@truck-dispatch/shared';

interface TenantState {
  selectedTenantId: string | null;
  selectedTenant: Tenant | null;
  tenants: Tenant[];
  setSelectedTenant: (tenant: Tenant | null) => void;
  setTenants: (tenants: Tenant[]) => void;
}

export const useTenantStore = create<TenantState>()(
  persist(
    (set) => ({
      selectedTenantId: null,
      selectedTenant: null,
      tenants: [],
      setSelectedTenant: (tenant) => set({ selectedTenant: tenant, selectedTenantId: tenant?.id || null }),
      setTenants: (tenants) => set({ tenants }),
    }),
    {
      name: 'tenant-store',
      partialize: (state) => ({ selectedTenantId: state.selectedTenantId, selectedTenant: state.selectedTenant }),
    }
  )
);
