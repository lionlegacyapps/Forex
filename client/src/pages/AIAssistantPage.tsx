import { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Brain, Send, Zap, TrendingUp, Package, Truck, DollarSign, RotateCcw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import api from '../lib/api';
import { useTenantStore } from '../store/tenant';
import type { Load, Driver } from '@truck-dispatch/shared';
import { formatCurrency } from '../lib/utils';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

const QUICK_PROMPTS = [
  { icon: Truck, label: 'Best driver for next load?', prompt: 'Which available driver is the best match for the next available load? Consider HOS hours, location, and equipment.' },
  { icon: TrendingUp, label: 'Rate analysis today', prompt: 'What are current market rates for our active lanes? Should we accept the current offers or negotiate higher?' },
  { icon: Package, label: 'HOS compliance check', prompt: 'Check all drivers for HOS compliance. Who is approaching their limits and needs rest?' },
  { icon: DollarSign, label: 'Revenue optimization', prompt: 'How can we optimize revenue this week? Which lanes should we prioritize and which loads should we decline?' },
];

export default function AIAssistantPage() {
  const { selectedTenant } = useTenantStore();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `**Welcome to TruckDispatch AI Assistant** 🚛\n\nI'm powered by DeepSeek AI and have real-time access to your fleet data. I can help you with:\n\n- **Load matching** — finding the best driver for each load\n- **Rate negotiation** — analyzing market rates and suggesting optimal pricing\n- **HOS monitoring** — tracking driver hours of service compliance\n- **Route optimization** — weather, tolls, restrictions\n- **Broker communications** — drafting messages and check-calls\n\nHow can I help you today?`,
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Rate suggestion tool
  const [showRateTool, setShowRateTool] = useState(false);
  const [rateTool, setRateTool] = useState({
    originCity: '', originState: '', destCity: '', destState: '',
    equipmentType: 'DRY_VAN', miles: '', weight: '',
  });
  const [rateResult, setRateResult] = useState<{ suggestedRate: number; minRate: number; maxRate: number; ratePerMile: number; factors: string[] } | null>(null);

  const { data: driversData } = useQuery({
    queryKey: ['drivers', selectedTenant?.id],
    queryFn: async () => {
      const { data } = await api.get(`/drivers${selectedTenant ? `?tenantId=${selectedTenant.id}` : ''}`);
      return data.data as Driver[];
    },
  });

  const { data: loadsData } = useQuery({
    queryKey: ['loads', selectedTenant?.id, 'active'],
    queryFn: async () => {
      const params = selectedTenant ? `?tenantId=${selectedTenant.id}&status=AVAILABLE&limit=10` : '?status=AVAILABLE&limit=10';
      const { data } = await api.get(`/loads${params}`);
      return data.data as Load[];
    },
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (text?: string) => {
    const content = text || input.trim();
    if (!content || loading) return;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content, timestamp: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const context = {
        tenantName: selectedTenant?.name || 'All Companies',
        availableDrivers: driversData?.filter((d) => d.status === 'AVAILABLE').length || 0,
        activeLoads: loadsData?.length || 0,
        drivers: driversData?.slice(0, 5).map((d) => ({
          name: d.name, status: d.status, location: `${d.currentCity}, ${d.currentState}`,
          driveRemaining: d.hosDriveRemaining, truckNumber: d.truckNumber,
        })),
      };

      const { data } = await api.post('/ai/chat', {
        messages: messages.filter((m) => m.id !== 'welcome').concat(userMsg).map((m) => ({ role: m.role, content: m.content })),
        context,
      });

      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.data.message,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date(),
      }]);
    } finally {
      setLoading(false);
    }
  };

  const getRateSuggestion = async () => {
    try {
      const { data } = await api.post('/ai/suggest-rate', {
        ...rateTool,
        miles: parseFloat(rateTool.miles),
        weight: parseFloat(rateTool.weight),
      });
      setRateResult(data.data);
    } catch {
      console.error('Rate suggestion failed');
    }
  };

  return (
    <div className="h-full flex gap-6">
      {/* Chat */}
      <div className="flex-1 flex flex-col bg-card border border-border rounded-xl overflow-hidden">
        <div className="p-4 border-b border-border flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Brain size={16} className="text-primary" />
          </div>
          <div>
            <h1 className="text-sm font-semibold">AI Dispatch Assistant</h1>
            <p className="text-xs text-muted-foreground">Powered by DeepSeek AI</p>
          </div>
          <div className="ml-auto flex items-center gap-1.5 text-xs text-green-400">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 pulse-dot" />
            Online
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center mr-2 mt-0.5 flex-shrink-0">
                  <Brain size={12} className="text-primary" />
                </div>
              )}
              <div className={`max-w-[80%] rounded-xl px-4 py-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground rounded-tr-sm'
                  : 'bg-secondary border border-border rounded-tl-sm'
              }`}>
                {msg.role === 'assistant' ? (
                  <div className="prose prose-sm prose-invert max-w-none">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p>{msg.content}</p>
                )}
                <p className={`text-[10px] mt-1 ${msg.role === 'user' ? 'text-primary-foreground/60' : 'text-muted-foreground'}`}>
                  {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex items-start gap-2">
              <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Brain size={12} className="text-primary" />
              </div>
              <div className="bg-secondary border border-border rounded-xl rounded-tl-sm px-4 py-3">
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick prompts */}
        <div className="px-4 py-2 flex gap-2 overflow-x-auto border-t border-border/50">
          {QUICK_PROMPTS.map(({ icon: Icon, label, prompt }) => (
            <button
              key={label}
              onClick={() => sendMessage(prompt)}
              className="flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <Icon size={11} />
              {label}
            </button>
          ))}
          <button onClick={() => setMessages([messages[0]])}
            className="flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <RotateCcw size={11} />
            Clear
          </button>
        </div>

        {/* Input */}
        <div className="p-4 border-t border-border">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
              placeholder="Ask about loads, drivers, rates, compliance..."
              className="flex-1 h-10 px-3 rounded-lg border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || loading}
              className="w-10 h-10 rounded-lg bg-primary text-primary-foreground flex items-center justify-center hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Right panel: Rate tool + context */}
      <div className="w-72 flex flex-col gap-4">
        {/* Rate Negotiation Tool */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="p-3 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <DollarSign size={14} className="text-amber-400" />
              <span className="text-xs font-semibold">Rate Calculator</span>
            </div>
            <button onClick={() => setShowRateTool(!showRateTool)} className="text-xs text-primary">
              {showRateTool ? 'Hide' : 'Show'}
            </button>
          </div>
          {showRateTool && (
            <div className="p-3 space-y-2">
              {[
                { key: 'originCity', placeholder: 'Origin City' },
                { key: 'originState', placeholder: 'State (e.g. TX)' },
                { key: 'destCity', placeholder: 'Dest City' },
                { key: 'destState', placeholder: 'State (e.g. CA)' },
                { key: 'miles', placeholder: 'Miles', type: 'number' },
                { key: 'weight', placeholder: 'Weight (lbs)', type: 'number' },
              ].map(({ key, placeholder, type = 'text' }) => (
                <input key={key} type={type} placeholder={placeholder}
                  value={(rateTool as Record<string, string>)[key]}
                  onChange={(e) => setRateTool({ ...rateTool, [key]: e.target.value })}
                  className="w-full h-7 px-2 rounded border border-input bg-secondary/30 text-xs focus:outline-none focus:ring-1 focus:ring-primary" />
              ))}
              <select value={rateTool.equipmentType} onChange={(e) => setRateTool({ ...rateTool, equipmentType: e.target.value })}
                className="w-full h-7 px-2 rounded border border-input bg-secondary/30 text-xs focus:outline-none focus:ring-1 focus:ring-primary">
                {['DRY_VAN', 'REEFER', 'FLATBED', 'HOTSHOT'].map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <button onClick={getRateSuggestion}
                className="w-full h-7 rounded bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors flex items-center justify-center gap-1.5">
                <Zap size={12} />
                Get AI Rate
              </button>
              {rateResult && (
                <div className="mt-2 p-2 rounded-lg bg-secondary/50 border border-border space-y-1.5">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Suggested Rate</span>
                    <span className="font-bold text-green-400">{formatCurrency(rateResult.suggestedRate)}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Per Mile</span>
                    <span className="font-semibold">${rateResult.ratePerMile.toFixed(2)}/mi</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Range</span>
                    <span className="text-muted-foreground">{formatCurrency(rateResult.minRate)} – {formatCurrency(rateResult.maxRate)}</span>
                  </div>
                  <div className="pt-1 border-t border-border/50 space-y-0.5">
                    {rateResult.factors.slice(0, 2).map((f, i) => (
                      <p key={i} className="text-[10px] text-muted-foreground">• {f}</p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Fleet context */}
        <div className="bg-card border border-border rounded-xl p-3">
          <p className="text-xs font-semibold mb-2 text-muted-foreground">Fleet Context</p>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Available Drivers</span>
              <span className="font-semibold text-green-400">{driversData?.filter((d) => d.status === 'AVAILABLE').length || 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Driving Now</span>
              <span className="font-semibold text-amber-400">{driversData?.filter((d) => d.status === 'DRIVING').length || 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Available Loads</span>
              <span className="font-semibold text-blue-400">{loadsData?.length || 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">HOS Alerts</span>
              <span className="font-semibold text-red-400">
                {driversData?.filter((d) => d.hosDriveRemaining < 4).length || 0}
              </span>
            </div>
          </div>
        </div>

        {/* Drivers list */}
        <div className="bg-card border border-border rounded-xl p-3 flex-1 overflow-hidden">
          <p className="text-xs font-semibold mb-2 text-muted-foreground">Available Drivers</p>
          <div className="space-y-2 overflow-y-auto max-h-64">
            {(driversData || []).filter((d) => d.status === 'AVAILABLE').map((d) => (
              <div key={d.id} className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium">{d.name}</p>
                  <p className="text-[10px] text-muted-foreground">{d.currentCity}, {d.currentState}</p>
                </div>
                <span className="text-[10px] text-green-400 font-semibold">{d.hosDriveRemaining.toFixed(1)}h</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
