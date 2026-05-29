import { Router, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { authenticate, AuthRequest, resolveTenant } from '../middleware/auth';

const router = Router();
const prisma = new PrismaClient();

router.use(authenticate);

router.get('/', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const where: Record<string, unknown> = {};
    if (tenantId) where.tenantId = tenantId;
    if (req.query.unread === 'true') where.isRead = false;

    const alerts = await prisma.alert.findMany({
      where,
      orderBy: { createdAt: 'desc' },
      take: 50,
    });
    return res.json({ success: true, data: alerts });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.post('/:id/read', async (req: AuthRequest, res: Response) => {
  try {
    await prisma.alert.update({ where: { id: req.params.id }, data: { isRead: true } });
    return res.json({ success: true });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.post('/read-all', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const where: Record<string, unknown> = { isRead: false };
    if (tenantId) where.tenantId = tenantId;
    await prisma.alert.updateMany({ where, data: { isRead: true } });
    return res.json({ success: true });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

export { router as alertsRouter };
