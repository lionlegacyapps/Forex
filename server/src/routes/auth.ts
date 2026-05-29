import { Router, Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { PrismaClient } from '@prisma/client';
import { authenticate, AuthRequest } from '../middleware/auth';

const router = Router();
const prisma = new PrismaClient();

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret';
const JWT_REFRESH_SECRET = process.env.JWT_REFRESH_SECRET || 'dev-refresh-secret';

function signAccess(user: { id: string; email: string; role: string; tenantId?: string | null }) {
  return jwt.sign(
    { id: user.id, email: user.email, role: user.role, tenantId: user.tenantId },
    JWT_SECRET,
    { expiresIn: '15m' }
  );
}

function signRefresh(userId: string) {
  return jwt.sign({ userId }, JWT_REFRESH_SECRET, { expiresIn: '7d' });
}

router.post('/login', async (req: Request, res: Response) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) {
      return res.status(400).json({ success: false, error: 'Email and password required' });
    }

    const user = await prisma.user.findUnique({
      where: { email },
      include: { tenant: true },
    });

    if (!user || !user.isActive) {
      return res.status(401).json({ success: false, error: 'Invalid credentials' });
    }

    const valid = await bcrypt.compare(password, user.password);
    if (!valid) {
      return res.status(401).json({ success: false, error: 'Invalid credentials' });
    }

    const accessToken = signAccess(user);
    const refreshToken = signRefresh(user.id);

    await prisma.refreshToken.create({
      data: {
        token: refreshToken,
        userId: user.id,
        expiresAt: new Date(Date.now() + 7 * 24 * 3600 * 1000),
      },
    });

    const { password: _p, ...safeUser } = user;
    return res.json({
      success: true,
      data: {
        accessToken,
        refreshToken,
        user: safeUser,
      },
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.post('/refresh', async (req: Request, res: Response) => {
  try {
    const { refreshToken } = req.body;
    if (!refreshToken) {
      return res.status(400).json({ success: false, error: 'Refresh token required' });
    }

    const stored = await prisma.refreshToken.findUnique({
      where: { token: refreshToken },
      include: { user: { include: { tenant: true } } },
    });

    if (!stored || stored.expiresAt < new Date()) {
      return res.status(401).json({ success: false, error: 'Invalid or expired refresh token' });
    }

    const payload = jwt.verify(refreshToken, JWT_REFRESH_SECRET) as { userId: string };
    if (payload.userId !== stored.userId) {
      return res.status(401).json({ success: false, error: 'Token mismatch' });
    }

    await prisma.refreshToken.delete({ where: { token: refreshToken } });

    const newAccessToken = signAccess(stored.user);
    const newRefreshToken = signRefresh(stored.user.id);

    await prisma.refreshToken.create({
      data: {
        token: newRefreshToken,
        userId: stored.user.id,
        expiresAt: new Date(Date.now() + 7 * 24 * 3600 * 1000),
      },
    });

    const { password: _p, ...safeUser } = stored.user;
    return res.json({
      success: true,
      data: { accessToken: newAccessToken, refreshToken: newRefreshToken, user: safeUser },
    });
  } catch {
    return res.status(401).json({ success: false, error: 'Invalid refresh token' });
  }
});

router.post('/logout', authenticate, async (req: AuthRequest, res: Response) => {
  try {
    const { refreshToken } = req.body;
    if (refreshToken) {
      await prisma.refreshToken.deleteMany({ where: { token: refreshToken } });
    }
    return res.json({ success: true, message: 'Logged out' });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.get('/me', authenticate, async (req: AuthRequest, res: Response) => {
  try {
    const user = await prisma.user.findUnique({
      where: { id: req.user!.id },
      include: { tenant: true },
    });
    if (!user) return res.status(404).json({ success: false, error: 'User not found' });
    const { password: _p, ...safeUser } = user;
    return res.json({ success: true, data: safeUser });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

export { router as authRouter };
