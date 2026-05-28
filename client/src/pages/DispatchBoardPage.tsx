import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Package, Truck, Plus, Zap, Phone, MessageSquare } from 'lucide-react';
import api from '../lib/api';
import { useTenantStore } from '../store/tenant';
import { formatCurrency, getStatusColor, getStatusDot } from '../lib/utils';
import type { Load, Driver } from '@truck-dispatch/shared';

const COLUMNS: { status: string; label: string; color: string }[] = [
  { status: 'AVAILABLE', label: 'Available', color: 'text-green-400' },
  { status: 'ASSIGNED', label: 'Assigned', color: 'text-blue-400' },
  { status: 'IN_TRANSIT', label: 'In Transit', color: 'text-amber-400' },
  { status: 'AT_PICKUP', label: 'At Pickup', color: 'text-orange-400' },
  { status: 'AT_DELIVERY', label: 'At Delivery', color: 'text-purple-400' },
  { status: 'DELIVERED', label: 'Delivered', color: 'text-emerald-400' },
];

function LoadCard({ load, drivers, onStatusChange, onAssign }: {
  load: Load;
  drivers: Driver[];
  onStatusChange: (id: string, status: string, driverId?: string) => void;
  onAssign: (load: Load) => void;
}) {
  const pickup = load.stops?.[0];
  const delivery = load.stops?.find((s) => s.type === 'DELIVERY');

  const nextStatus: Record<string, string> = {
    AVAILABLE: 'ASSIGNED',
    ASSIGNED: 'IN_TRANSIT',
    IN_TRANSIT: 'AT_DELIVERY',
    AT_PICKUP: 'IN_TRANSIT',
    AT_DELIVERY: 'DELIVERED',
  };

  return (
    <div className="bg-card border border-border rounded-lg p-3 space-y-2 hover:border-primary/30 transition-colors cursor-pointer slide-in">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold font-mono text-primary">{load.loadNumber}</span>
        <span className="text-xs text-muted-foreground">{load.equipmentType.replace('_', ' ')}</span>
      </div>

      {pickup && delivery && (
        <div className="space-y-0.5">
          <div className="flex items-center gap-1.5 text-xs">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />
            <span className="text-foreground font-medium truncate">{pickup.city}, {pickup.state}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <div className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
            <span className="text-muted-foreground truncate">{delivery.city}, {delivery.state}</span>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{load.miles ? `${Math.round(load.miles)} mi` : '—'}</span>
        <span className="text-foreground font-semibold">{formatCurrency(load.rate)}</span>
      </div>

      {load.driver ? (
        <div className="flex items-center gap-2 pt-1 border-t border-border/50">
          <div className={`w-1.5 h-1.5 rounded-full ${getStatusDot(load.driver.status || '')}`} />
          <span className="text-xs text-muted-foreground flex-1 truncate">{load.driver.name}</span>
          <button
            onClick={(e) => { e.stopPropagation(); api.post('/integrations/telnyx/sms', { to: load.driver!.phone, message: `Check-call: Load ${load.loadNumber}`, driverId: load.driver!.id }); }}
            className="p-1 rounded hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground"
            title="Send SMS"
          >
            <MessageSquare size={10} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); }}
            className="p-1 rounded hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground"
            title="Call driver"
          >
            <Phone size={10} />
          </button>
        </div>
      ) : (
        <button
          onClick={(e) => { e.stopPropagation(); onAssign(load); }}
          className="w-full mt-1 flex items-center justify-center gap-1.5 py-1 rounded border border-primary/30 text-primary text-xs hover:bg-primary/5 transition-colors"
        >
          <Zap size={10} />
          Assign Driver
        </button>
      )}

      {nextStatus[load.status] && (
        <button
          onClick={(e) => { e.stopPropagation(); onStatusChange(load.id, nextStatus[load.status]); }}
          className="w-full py-1 rounded bg-secondary/60 hover:bg-secondary text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          → {nextStatus[load.status].replace('_', ' ')}
        </button>
      )}
    </div>
  );
}

function AssignModal({ load, drivers, onClose, onAssign }: {
  load: Load;
  drivers: Driver[];
  onClose: () => void;
  onAssign: (loadId: string, driverId: string) => void;
}) {
  const [selectedDriver, setSelectedDriver] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResults, setAiResults] = useState<{ driverId: string; driver: Driver; score: number; reasons: string[] }[]>([]);

  const runAI = async () => {
    setAiLoading(true);
    try {
      const { data } = await api.post('/ai/match-load', { loadId: load.id });
      setAiResults(data.data);
    } catch {
      console.error('AI match failed');
    } finally {
      setAiLoading(false);
    }
  };

  const availableDrivers = drivers.filter((d) => d.status === 'AVAILABLE' || d.status === 'ON_DUTY');

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg shadow-2xl">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">Assign Driver — {load.loadNumber}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-xl">×</button>
        </div>
        <div className="p-4 space-y-4">
          {/* AI Match button */}
          <button
            onClick={runAI}
            disabled={aiLoading}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-sm font-medium hover:bg-primary/20 transition-colors disabled:opacity-50"
          >
            {aiLoading ? <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" /> : <Zap size={16} />}
            {aiLoading ? 'Analyzing...' : 'AI Match — Find Best Driver'}
          </button>

          {/* AI results */}
          {aiResults.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground">AI Recommendations</p>
              {aiResults.slice(0, 3).map((r) => (
                <button
                  key={r.driverId}
                  onClick={() => { setSelectedDriver(r.driverId); onAssign(load.id, r.driverId); }}
                  className="w-full text-left p-3 rounded-lg border border-border hover:border-primary/30 hover:bg-primary/5 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-semibold">{r.driver.name}</span>
                    <span className="text-xs font-bold text-primary">{r.score}/100</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {r.reasons.slice(0, 2).map((reason, i) => (
                      <span key={i} className="text-[10px] bg-secondary px-2 py-0.5 rounded">{reason}</span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Manual select */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground mb-2">Or select manually</p>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {availableDrivers.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDriver(d.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${selectedDriver === d.id ? 'border-primary bg-primary/10' : 'border-border hover:border-border/60'}`}
                >
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${getStatusDot(d.status)}`} />
                    <span className="text-sm font-medium">{d.name}</span>
                    <span className="text-xs text-muted-foreground ml-auto">{d.hosDriveRemaining.toFixed(1)}h drive</span>
                  </div>
                  <p className="text-xs text-muted-foreground ml-4">{d.currentCity}, {d.currentState} • {d.truckNumber}</p>
                </button>
              ))}
            </div>
          </div>

          {selectedDriver && (
            <button
              onClick={() => onAssign(load.id, selectedDriver)}
              className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              Confirm Assignment
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DispatchBoardPage() {
  const { selectedTenant } = useTenantStore();
  const queryClient = useQueryClient();
  const [assigningLoad, setAssigningLoad] = useState<Load | null>(null);

  const tenantQuery = selectedTenant ? `?tenantId=${selectedTenant.id}` : '';

  const { data: loadsData } = useQuery({
    queryKey: ['loads', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/loads${tenantQuery}&limit=100`);
      return data.data as Load[];
    },
    refetchInterval: 30000,
  });

  const { data: driversData } = useQuery({
    queryKey: ['drivers', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/drivers${tenantQuery}`);
      return data.data as Driver[];
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status, driverId }: { id: string; status: string; driverId?: string }) =>
      api.post(`/loads/${id}/status`, { status, driverId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['loads'] }),
  });

  const assignMutation = useMutation({
    mutationFn: ({ loadId, driverId }: { loadId: string; driverId: string }) =>
      api.post(`/loads/${loadId}/status`, { status: 'ASSIGNED', driverId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loads'] });
      queryClient.invalidateQueries({ queryKey: ['drivers'] });
      setAssigningLoad(null);
    },
  });

  const loads = loadsData || [];
  const drivers = driversData || [];

  const getColumnLoads = (status: string) =>
    loads.filter((l) => l.status === status);

  return (
    <div className="space-y-4 h-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dispatch Board</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Kanban view — drag to update load status</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Truck size={14} />
            <span>{drivers.filter((d) => d.status === 'AVAILABLE').length} available</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Package size={14} />
            <span>{loads.filter((l) => !['DELIVERED', 'CANCELLED'].includes(l.status)).length} active</span>
          </div>
        </div>
      </div>

      {/* Kanban Board */}
      <div className="flex gap-4 overflow-x-auto pb-4" style={{ minHeight: '70vh' }}>
        {COLUMNS.map((col) => {
          const colLoads = getColumnLoads(col.status);
          return (
            <div key={col.status} className="flex-shrink-0 w-64 flex flex-col">
              {/* Column header */}
              <div className="flex items-center justify-between mb-3 px-1">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${getStatusDot(col.status)}`} />
                  <span className={`text-sm font-semibold ${col.color}`}>{col.label}</span>
                </div>
                <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">
                  {colLoads.length}
                </span>
              </div>

              {/* Cards */}
              <div className="flex-1 space-y-2 bg-secondary/20 rounded-xl p-2 min-h-40">
                {colLoads.map((load) => (
                  <LoadCard
                    key={load.id}
                    load={load}
                    drivers={drivers}
                    onStatusChange={(id, status) => statusMutation.mutate({ id, status })}
                    onAssign={setAssigningLoad}
                  />
                ))}
                {colLoads.length === 0 && (
                  <div className="h-24 flex items-center justify-center">
                    <p className="text-xs text-muted-foreground/50">No loads</p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {assigningLoad && (
        <AssignModal
          load={assigningLoad}
          drivers={drivers}
          onClose={() => setAssigningLoad(null)}
          onAssign={(loadId, driverId) => assignMutation.mutate({ loadId, driverId })}
        />
      )}
    </div>
  );
}
