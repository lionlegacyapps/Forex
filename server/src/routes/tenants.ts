import { Router, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { authenticate, requireRole, AuthRequest } from '../middleware/auth';

const router = Router();
const prisma = new PrismaClient();

router.use(authenticate);

router.get('/', async (req: AuthRequest, res: Response) => {
  try {
    const tenants = await prisma.tenant.findMany({
      include: {
        _count: { select: { drivers: true, loads: true, users: true } },
      },
      orderBy: { name: 'asc' },
    });
    return res.json({ success: true, data: tenants });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.get('/:id', async (req: AuthRequest, res: Response) => {
  try {
    const tenant = await prisma.tenant.findUnique({
      where: { id: req.params.id },
      include: {
        _count: { select: { drivers: true, loads: true, users: true } },
        settings: true,
      },
    });
    if (!tenant) return res.status(404).json({ success: false, error: 'Tenant not found' });
    return res.json({ success: true, data: tenant });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.post('/', requireRole('SUPER_DISPATCHER'), async (req: AuthRequest, res: Response) => {
  try {
    const { name, dotNumber, mcNumber, address, phone, email, operationType } = req.body;
    if (!name) return res.status(400).json({ success: false, error: 'Name is required' });

    const tenant = await prisma.tenant.create({
      data: { name, dotNumber, mcNumber, address, phone, email, operationType: operationType || 'MIXED' },
    });
    return res.status(201).json({ success: true, data: tenant });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.put('/:id', requireRole('SUPER_DISPATCHER', 'COMPANY_ADMIN'), async (req: AuthRequest, res: Response) => {
  try {
    const { name, dotNumber, mcNumber, address, phone, email, operationType, isActive } = req.body;
    const tenant = await prisma.tenant.update({
      where: { id: req.params.id },
      data: { name, dotNumber, mcNumber, address, phone, email, operationType, isActive },
    });
    return res.json({ success: true, data: tenant });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.delete('/:id', requireRole('SUPER_DISPATCHER'), async (req: AuthRequest, res: Response) => {
  try {
    await prisma.tenant.update({ where: { id: req.params.id }, data: { isActive: false } });
    return res.json({ success: true, message: 'Tenant deactivated' });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

export { router as tenantsRouter };
