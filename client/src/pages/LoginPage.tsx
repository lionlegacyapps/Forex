import { useState, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Truck, Eye, EyeOff, Zap } from 'lucide-react';
import { useAuthStore } from '../store/auth';

export default function LoginPage() {
  const [email, setEmail] = useState('admin@dispatch.com');
  const [password, setPassword] = useState('dispatch123');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch {
      setError('Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  const demoAccounts = [
    { label: 'Super Dispatcher', email: 'admin@dispatch.com', role: 'Full access — all companies' },
    { label: 'Alpha Logistics', email: 'dispatcher@alphalogistics.com', role: 'Long-haul dispatcher' },
    { label: 'Swift Local', email: 'dispatcher@swiftlocal.com', role: 'Local delivery dispatcher' },
  ];

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      {/* Background grid */}
      <div
        className="absolute inset-0 opacity-5"
        style={{
          backgroundImage: 'linear-gradient(to right, hsl(212 95% 68%) 1px, transparent 1px), linear-gradient(to bottom, hsl(212 95% 68%) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      <div className="w-full max-w-md relative">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 mb-4">
            <Truck size={32} className="text-primary" />
          </div>
          <h1 className="text-3xl font-bold text-foreground">TruckDispatch AI</h1>
          <p className="text-muted-foreground mt-2">Advanced Multi-Tenant Dispatch Platform</p>
        </div>

        {/* Login card */}
        <div className="bg-card border border-border rounded-2xl p-8 shadow-2xl">
          <h2 className="text-xl font-semibold mb-6">Sign in to your account</h2>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full h-10 px-3 rounded-md border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="dispatcher@company.com"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-10 px-3 pr-10 rounded-md border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  Signing in...
                </>
              ) : (
                <>
                  <Zap size={16} />
                  Sign In
                </>
              )}
            </button>
          </form>

          {/* Demo accounts */}
          <div className="mt-6 pt-6 border-t border-border">
            <p className="text-xs text-muted-foreground mb-3 font-medium">Demo Accounts (password: dispatch123)</p>
            <div className="space-y-2">
              {demoAccounts.map((acc) => (
                <button
                  key={acc.email}
                  type="button"
                  onClick={() => { setEmail(acc.email); setPassword('dispatch123'); }}
                  className="w-full text-left px-3 py-2 rounded-lg border border-border hover:border-primary/30 hover:bg-primary/5 transition-colors"
                >
                  <p className="text-xs font-semibold text-foreground">{acc.label}</p>
                  <p className="text-xs text-muted-foreground">{acc.role}</p>
                </button>
              ))}
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-6">
          Powered by DeepSeek AI • HERE Maps • Samsara • Telnyx
        </p>
      </div>
    </div>
  );
}
