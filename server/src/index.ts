import dotenv from 'dotenv';
import path from 'path';
// Load from server/.env first (CWD when running from server/), then root
dotenv.config({ path: path.resolve(process.cwd(), '.env') });
dotenv.config({ path: path.resolve(__dirname, '../.env') });
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

import express from 'express';
import cors from 'cors';
import { authRouter } from './routes/auth';
import { tenantsRouter } from './routes/tenants';
import { driversRouter } from './routes/drivers';
import { loadsRouter } from './routes/loads';
import { aiRouter } from './routes/ai';
import { documentsRouter } from './routes/documents';
import { integrationsRouter } from './routes/integrations';
import { dashboardRouter } from './routes/dashboard';
import { alertsRouter } from './routes/alerts';

dotenv.config({ path: path.join(__dirname, '../../.env') });

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors({
  origin: ['http://localhost:5173', 'http://localhost:3000'],
  credentials: true,
}));

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Serve uploaded files
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
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
  console.log(`🚛 TruckDispatch AI server running on http://localhost:${PORT}`);
});

export default app;
