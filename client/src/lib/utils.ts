import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 }).format(amount);
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('en-US').format(n);
}

export function formatMiles(miles: number): string {
  return `${new Intl.NumberFormat('en-US').format(Math.round(miles))} mi`;
}

export function formatDate(dateStr: string | Date): string {
  const d = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function formatTime(dateStr: string | Date): string {
  const d = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

export function formatDateTime(dateStr: string | Date): string {
  return `${formatDate(dateStr)} ${formatTime(dateStr)}`;
}

export function timeAgo(dateStr: string | Date): string {
  const d = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    AVAILABLE: 'text-green-400 bg-green-400/10 border-green-400/20',
    ASSIGNED: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
    IN_TRANSIT: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
    AT_PICKUP: 'text-orange-400 bg-orange-400/10 border-orange-400/20',
    AT_DELIVERY: 'text-purple-400 bg-purple-400/10 border-purple-400/20',
    DELIVERED: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
    CANCELLED: 'text-red-400 bg-red-400/10 border-red-400/20',
    ON_DUTY: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
    DRIVING: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
    OFF_DUTY: 'text-slate-400 bg-slate-400/10 border-slate-400/20',
    SLEEPER: 'text-indigo-400 bg-indigo-400/10 border-indigo-400/20',
  };
  return map[status] || 'text-slate-400 bg-slate-400/10 border-slate-400/20';
}

export function getStatusDot(status: string): string {
  const map: Record<string, string> = {
    AVAILABLE: 'bg-green-400',
    ASSIGNED: 'bg-blue-400',
    IN_TRANSIT: 'bg-amber-400',
    AT_PICKUP: 'bg-orange-400',
    AT_DELIVERY: 'bg-purple-400',
    DELIVERED: 'bg-emerald-400',
    CANCELLED: 'bg-red-400',
    ON_DUTY: 'bg-blue-400',
    DRIVING: 'bg-amber-400',
    OFF_DUTY: 'bg-slate-400',
    SLEEPER: 'bg-indigo-400',
  };
  return map[status] || 'bg-slate-400';
}

export function hosColor(hours: number): string {
  if (hours >= 8) return 'text-green-400';
  if (hours >= 4) return 'text-amber-400';
  return 'text-red-400';
}

export function hosBarColor(hours: number, max: number): string {
  const pct = hours / max;
  if (pct >= 0.6) return 'bg-green-400';
  if (pct >= 0.3) return 'bg-amber-400';
  return 'bg-red-400';
}
