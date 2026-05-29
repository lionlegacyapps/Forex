import express from 'express';
import cors from 'cors';
import path from 'path';
import { authRouter } from './routes/auth';
import { tenantsRouter } from './routes/tenants';
import { driversRouter } from './routes/drivers';
import { loadsRouter } from './routes/loads';
import { aiRouter } from './routes/ai';
import { documentsRouter } from './routes/documents';
import { integrationsRouter } from './routes/integrations';
import { dashboardRouter } from './routes/dashboard';
import { alertsRouter } from './routes/alerts';

const app = express();

const allowedOrigins = [
  'http://localhost:5173',
  'http://localhost:3000',
  process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : '',
  process.env.CLIENT_URL || '',
].filter(Boolean);

app.use(cors({
  origin: (origin, callback) => {
    // Allow requests with no origin (mobile apps, curl, etc.)
    if (!origin) return callback(null, true);
    // Allow any vercel.app or localhost origin
    if (
      allowedOrigins.includes(origin) ||
      origin.endsWith('.vercel.app') ||
      origin.includes('localhost')
    ) {
      return callback(null, true);
    }
    callback(null, true); // permissive for demo — restrict in production
  },
  credentials: true,
}));

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Serve uploaded files (local dev only — use S3/Cloudinary in production)
app.use('/uploads', express.static(path.join(__dirname, '../uploads')));

// Routes
app.use('/api/auth', authRouter);
app.use('/api/tenants', tenantsRouter);
app.use('/api/drivers', driversRouter);
app.use('/api/loads', loadsRouter);
app.use('/api/ai', aiRouter);
app.use('/api/documents', documentsRouter);
app.use('/api/integrations', integrationsRouter);
app.use('/api/dashboard', dashboardRouter);
app.use('/api/alerts', alertsRouter);

app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    env: process.env.NODE_ENV || 'development',
  });
});

export default app;
