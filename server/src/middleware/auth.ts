import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';

export interface AuthRequest extends Request {
  user?: {
    id: string;
    email: string;
    role: string;
    tenantId?: string;
  };
}

export function authenticate(req: AuthRequest, res: Response, next: NextFunction) {
  const authHeader = req.headers.authorization;
  if (!authHeader?.startsWith('Bearer ')) {
    return res.status(401).json({ success: false, error: 'No token provided' });
  }

  const token = authHeader.slice(7);
  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET || 'dev-secret') as {
      id: string;
      email: string;
      role: string;
      tenantId?: string;
    };
    req.user = payload;
    next();
  } catch {
    return res.status(401).json({ success: false, error: 'Invalid or expired token' });
  }
}

export function requireRole(...roles: string[]) {
  return (req: AuthRequest, res: Response, next: NextFunction) => {
    if (!req.user || !roles.includes(req.user.role)) {
      return res.status(403).json({ success: false, error: 'Insufficient permissions' });
    }
    next();
  };
}

// Resolves tenantId: from query param (super-dispatcher) or from JWT (regular user)
export function resolveTenant(req: AuthRequest): string | undefined {
  if (req.user?.role === 'SUPER_DISPATCHER') {
    return (req.query.tenantId as string) || (req.body?.tenantId as string) || undefined;
  }
  return req.user?.tenantId;
}
