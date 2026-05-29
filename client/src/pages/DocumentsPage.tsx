import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useRef } from 'react';
import { FileText, Upload, X, CheckCircle, Clock, AlertCircle, Eye } from 'lucide-react';
import api from '../lib/api';
import { useTenantStore } from '../store/tenant';
import { formatDate, timeAgo } from '../lib/utils';

const DOC_TYPES = ['BOL', 'RATE_CONFIRMATION', 'POD', 'INVOICE', 'OTHER'];

export default function DocumentsPage() {
  const { selectedTenant } = useTenantStore();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [typeFilter, setTypeFilter] = useState('');
  const [uploading, setUploading] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Record<string, unknown> | null>(null);
  const [uploadForm, setUploadForm] = useState({ type: 'RATE_CONFIRMATION', loadId: '' });

  const { data: docsData, isLoading } = useQuery({
    queryKey: ['documents', selectedTenant?.id, typeFilter],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (selectedTenant) params.set('tenantId', selectedTenant.id);
      if (typeFilter) params.set('type', typeFilter);
      const { data } = await api.get(`/documents?${params}`);
      return data.data as Record<string, unknown>[];
    },
    refetchInterval: 5000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/documents/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
  });

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', uploadForm.type);
    if (selectedTenant) formData.append('tenantId', selectedTenant.id);
    if (uploadForm.loadId) formData.append('loadId', uploadForm.loadId);

    try {
      await api.post('/documents/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    } catch (err) {
      console.error(err);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const docs = docsData || [];
  const statusIcons: Record<string, React.ElementType> = {
    DONE: CheckCircle,
    PROCESSING: Clock,
    PENDING: Clock,
    FAILED: AlertCircle,
  };
  const statusColors: Record<string, string> = {
    DONE: 'text-green-400',
    PROCESSING: 'text-amber-400',
    PENDING: 'text-blue-400',
    FAILED: 'text-red-400',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Document Center</h1>
          <p className="text-sm text-muted-foreground">AI-powered document parsing for BOLs, Rate Cons, and PODs</p>
        </div>
      </div>

      {/* Upload section */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold mb-4">Upload Document</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Document Type</label>
            <select value={uploadForm.type} onChange={(e) => setUploadForm({ ...uploadForm, type: e.target.value })}
              className="w-full h-9 px-3 rounded-lg border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary">
              {DOC_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Load ID (optional)</label>
            <input type="text" value={uploadForm.loadId} onChange={(e) => setUploadForm({ ...uploadForm, loadId: e.target.value })}
              placeholder="Associate with a load"
              className="w-full h-9 px-3 rounded-lg border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
          </div>
          <div className="flex items-end">
            <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={handleUpload} className="hidden" />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="w-full h-9 rounded-lg border border-dashed border-primary/40 text-primary text-sm flex items-center justify-center gap-2 hover:bg-primary/5 transition-colors disabled:opacity-50"
            >
              {uploading ? (
                <><div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />Uploading...</>
              ) : (
                <><Upload size={16} />Choose File</>
              )}
            </button>
          </div>
        </div>

        <div
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-border rounded-xl p-8 text-center hover:border-primary/40 transition-colors cursor-pointer"
        >
          <Upload size={24} className="text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Drop PDF, JPG, or PNG files here</p>
          <p className="text-xs text-muted-foreground/60 mt-1">AI will automatically extract data from the document</p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        <button onClick={() => setTypeFilter('')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${!typeFilter ? 'bg-primary/10 text-primary' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}>
          All
        </button>
        {DOC_TYPES.map((t) => (
          <button key={t} onClick={() => setTypeFilter(t)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${typeFilter === t ? 'bg-primary/10 text-primary' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}>
            {t.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Documents grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {docs.map((doc) => {
          const StatusIcon = statusIcons[doc.parseStatus as string] || Clock;
          const statusColor = statusColors[doc.parseStatus as string] || 'text-muted-foreground';
          return (
            <div key={doc.id as string} className="bg-card border border-border rounded-xl p-4 hover:border-primary/20 transition-colors">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-secondary flex items-center justify-center">
                    <FileText size={14} className="text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold">{doc.type as string}</p>
                    <p className="text-[10px] text-muted-foreground truncate max-w-[140px]">{doc.fileName as string}</p>
                  </div>
                </div>
                <button onClick={() => deleteMutation.mutate(doc.id as string)}
                  className="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors">
                  <X size={12} />
                </button>
              </div>

              <div className="flex items-center gap-1.5 mb-3">
                <StatusIcon size={12} className={statusColor} />
                <span className={`text-xs font-medium ${statusColor}`}>{doc.parseStatus as string}</span>
                {doc.parseStatus === 'PROCESSING' && (
                  <div className="flex-1 h-1 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full bg-amber-400 rounded-full animate-pulse" style={{ width: '60%' }} />
                  </div>
                )}
              </div>

              {(doc.parseStatus as string) === 'DONE' && Boolean(doc.parsedData) && (
                <button
                  onClick={() => setSelectedDoc(doc as Record<string, unknown>)}
                  className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-green-400/10 text-green-400 text-xs hover:bg-green-400/20 transition-colors mb-2"
                >
                  <Eye size={12} />
                  View Parsed Data
                </button>
              )}

              <p className="text-[10px] text-muted-foreground">{timeAgo(doc.createdAt as string)}</p>
            </div>
          );
        })}
      </div>

      {docs.length === 0 && !isLoading && (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <FileText size={32} className="text-muted-foreground mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">No documents yet. Upload a BOL or rate confirmation to get started.</p>
        </div>
      )}

      {/* Parsed data modal */}
      {selectedDoc && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-xl w-full max-w-lg shadow-2xl">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold">Parsed Data — {selectedDoc.type as string}</h2>
              <button onClick={() => setSelectedDoc(null)}><X size={18} className="text-muted-foreground" /></button>
            </div>
            <div className="p-4 max-h-96 overflow-y-auto">
              <div className="space-y-2">
                {Object.entries((selectedDoc.parsedData as Record<string, unknown>) || {}).map(([key, value]) => (
                  <div key={key} className="flex gap-3">
                    <span className="text-xs font-semibold text-muted-foreground w-32 flex-shrink-0">{key.replace(/([A-Z])/g, ' $1').trim()}</span>
                    <span className="text-xs text-foreground">{typeof value === 'object' ? JSON.stringify(value) : String(value)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-4 border-t border-border">
                <button className="w-full py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors">
                  Auto-fill Load Form
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
