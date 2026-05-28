import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ExternalLink, RefreshCw, Zap, Filter, MapPin } from 'lucide-react';
import api from '../lib/api';
import { formatCurrency } from '../lib/utils';

interface LoadBoardEntry {
  id: string;
  origin: string;
  destination: string;
  miles: number;
  rate: number;
  equipmentType: string;
  weight: number;
  age: string;
  broker: string;
  contact: string;
}

export default function LoadBoardPage() {
  const [equipFilter, setEquipFilter] = useState('');
  const [importing, setImporting] = useState<string | null>(null);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['loadboard'],
    queryFn: async () => {
      const { data } = await api.get('/integrations/loadboard/available');
      return data.data as LoadBoardEntry[];
    },
    refetchInterval: 120000,
  });

  const loads = (data || []).filter((l) =>
    equipFilter ? l.equipmentType === equipFilter : true
  );

  const handleImport = async (load: LoadBoardEntry) => {
    setImporting(load.id);
    // Simulate import
    await new Promise((r) => setTimeout(r, 1000));
    alert(`Load from ${load.origin} → ${load.destination} imported to your load board!`);
    setImporting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Load Board</h1>
          <p className="text-sm text-muted-foreground">Available loads from DAT, Truckstop and brokers</p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-secondary text-sm font-medium hover:bg-secondary/80 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <button onClick={() => setEquipFilter('')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${!equipFilter ? 'bg-primary/10 text-primary' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}>
          All Equipment
        </button>
        {['DRY_VAN', 'REEFER', 'FLATBED', 'HOTSHOT'].map((t) => (
          <button key={t} onClick={() => setEquipFilter(equipFilter === t ? '' : t)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${equipFilter === t ? 'bg-primary/10 text-primary' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}>
            {t.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Load board */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="p-3 border-b border-border bg-secondary/30 flex items-center gap-2">
          <ExternalLink size={14} className="text-muted-foreground" />
          <span className="text-xs font-semibold text-muted-foreground">DAT LOAD BOARD (MOCK)</span>
          <div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 pulse-dot" />
            {loads.length} available loads
          </div>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Origin</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Destination</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Equipment</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Weight</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Miles</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Rate</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">$/mi</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Broker</th>
              <th className="text-left p-3 text-xs font-semibold text-muted-foreground">Age</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {loads.map((load) => (
              <tr key={load.id} className="border-b border-border/50 last:border-0 hover:bg-secondary/20 transition-colors">
                <td className="p-3">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
                    <span className="text-sm">{load.origin}</span>
                  </div>
                </td>
                <td className="p-3">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-red-400" />
                    <span className="text-sm">{load.destination}</span>
                  </div>
                </td>
                <td className="p-3 text-sm text-muted-foreground">{load.equipmentType.replace('_', ' ')}</td>
                <td className="p-3 text-sm text-muted-foreground">{load.weight.toLocaleString()} lbs</td>
                <td className="p-3 text-sm text-muted-foreground">{load.miles} mi</td>
                <td className="p-3">
                  <span className="text-sm font-bold text-green-400">{formatCurrency(load.rate)}</span>
                </td>
                <td className="p-3 text-sm text-muted-foreground">
                  ${(load.rate / load.miles).toFixed(2)}
                </td>
                <td className="p-3">
                  <div>
                    <p className="text-sm">{load.broker}</p>
                    <p className="text-xs text-muted-foreground">{load.contact}</p>
                  </div>
                </td>
                <td className="p-3 text-xs text-muted-foreground">{load.age}</td>
                <td className="p-3">
                  <button
                    onClick={() => handleImport(load)}
                    disabled={importing === load.id}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors disabled:opacity-50"
                  >
                    {importing === load.id ? (
                      <div className="w-3 h-3 border border-primary/30 border-t-primary rounded-full animate-spin" />
                    ) : (
                      <Zap size={11} />
                    )}
                    Import
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {loads.length === 0 && (
          <div className="p-12 text-center">
            <ExternalLink size={24} className="text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">No loads matching current filters</p>
          </div>
        )}
      </div>
    </div>
  );
}
