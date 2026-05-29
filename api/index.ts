// Vercel Serverless Function entry point
// This file wraps the Express app for deployment on Vercel

import type { VercelRequest, VercelResponse } from '@vercel/node';
import dotenv from 'dotenv';
import path from 'path';

// Load environment variables
dotenv.config();

// Import the Express app (must be imported AFTER dotenv)
import app from '../server/src/app';

export default function handler(req: VercelRequest, res: VercelResponse) {
  return app(req as any, res as any);
}
