import { Router, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { authenticate, AuthRequest, resolveTenant } from '../middleware/auth';

const router = Router();
const prisma = new PrismaClient();

router.use(authenticate);

router.get('/', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const { status, driverId, page = '1', limit = '50' } = req.query;

    const where: Record<string, unknown> = {};
    if (tenantId) where.tenantId = tenantId;
    if (status) where.status = status;
    if (driverId) where.driverId = driverId;

    const skip = (parseInt(page as string) - 1) * parseInt(limit as string);
    const [loads, total] = await Promise.all([
      prisma.load.findMany({
        where,
        include: {
          stops: { orderBy: { sequence: 'asc' } },
          driver: { select: { id: true, name: true, phone: true, truckNumber: true, status: true } },
          tenant: { select: { id: true, name: true } },
        },
        orderBy: { createdAt: 'desc' },
        skip,
        take: parseInt(limit as string),
      }),
      prisma.load.count({ where }),
    ]);

    return res.json({
      success: true,
      data: loads,
      total,
      page: parseInt(page as string),
      limit: parseInt(limit as string),
      totalPages: Math.ceil(total / parseInt(limit as string)),
    });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.get('/:id', async (req: AuthRequest, res: Response) => {
  try {
    const load = await prisma.load.findUnique({
      where: { id: req.params.id },
      include: {
        stops: { orderBy: { sequence: 'asc' } },
        driver: true,
        tenant: true,
        documents: true,
      },
    });
    if (!load) return res.status(404).json({ success: false, error: 'Load not found' });
    return res.json({ success: true, data: load });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

function generateLoadNumber(tenantName: string) {
  const prefix = tenantName.slice(0, 2).toUpperCase();
  const ts = Date.now().toString().slice(-6);
  return `${prefix}-${new Date().getFullYear()}-${ts}`;
}

router.post('/', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req) || req.body.tenantId;
    if (!tenantId) return res.status(400).json({ success: false, error: 'tenantId required' });

    const tenant = await prisma.tenant.findUnique({ where: { id: tenantId } });
    if (!tenant) return res.status(404).json({ success: false, error: 'Tenant not found' });

    const { stops, driverId, ...loadData } = req.body;

    const load = await prisma.load.create({
      data: {
        ...loadData,
        tenantId,
        driverId: driverId || undefined,
        loadNumber: loadData.loadNumber || generateLoadNumber(tenant.name),
        status: driverId ? 'ASSIGNED' : 'AVAILABLE',
      },
    });

    if (stops?.length) {
      await prisma.loadStop.createMany({
        data: stops.map((s: Record<string, unknown>, i: number) => ({
          ...s,
          loadId: load.id,
          sequence: i + 1,
          scheduledArrival: new Date(s.scheduledArrival as string),
          scheduledDeparture: s.scheduledDeparture ? new Date(s.scheduledDeparture as string) : undefined,
        })),
      });
    }

    const full = await prisma.load.findUnique({
      where: { id: load.id },
      include: { stops: { orderBy: { sequence: 'asc' } }, driver: true },
    });

    return res.status(201).json({ success: true, data: full });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.put('/:id', async (req: AuthRequest, res: Response) => {
  try {
    const { stops, ...loadData } = req.body;

    const load = await prisma.load.update({
      where: { id: req.params.id },
      data: loadData,
    });

    if (stops?.length) {
      await prisma.loadStop.deleteMany({ where: { loadId: load.id } });
      await prisma.loadStop.createMany({
        data: stops.map((s: Record<string, unknown>, i: number) => ({
          ...s,
          loadId: load.id,
          sequence: i + 1,
          scheduledArrival: new Date(s.scheduledArrival as string),
        })),
      });
    }

    const full = await prisma.load.findUnique({
      where: { id: load.id },
      include: { stops: { orderBy: { sequence: 'asc' } }, driver: true },
    });

    return res.json({ success: true, data: full });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

// Status transition endpoint
router.post('/:id/status', async (req: AuthRequest, res: Response) => {
  try {
    const { status, driverId } = req.body;
    const validStatuses = ['AVAILABLE', 'ASSIGNED', 'IN_TRANSIT', 'AT_PICKUP', 'AT_DELIVERY', 'DELIVERED', 'CANCELLED'];

    if (!validStatuses.includes(status)) {
      return res.status(400).json({ success: false, error: 'Invalid status' });
    }

    const updateData: Record<string, unknown> = { status };
    if (driverId !== undefined) updateData.driverId = driverId || null;
    if (status === 'IN_TRANSIT' || status === 'AT_PICKUP') updateData.pickedUpAt = new Date();
    if (status === 'DELIVERED') updateData.deliveredAt = new Date();

    const load = await prisma.load.update({
      where: { id: req.params.id },
      data: updateData,
      include: {
        stops: { orderBy: { sequence: 'asc' } },
        driver: { select: { id: true, name: true, phone: true } },
      },
    });

    // Update driver status based on load status
    if (load.driverId) {
      let driverStatus = 'AVAILABLE';
      if (status === 'ASSIGNED') driverStatus = 'ON_DUTY';
      if (status === 'IN_TRANSIT' || status === 'AT_PICKUP' || status === 'AT_DELIVERY') driverStatus = 'DRIVING';
      if (status === 'DELIVERED' || status === 'CANCELLED') driverStatus = 'AVAILABLE';
      await prisma.driver.update({ where: { id: load.driverId }, data: { status: driverStatus } });
    }

    return res.json({ success: true, data: load });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.delete('/:id', async (req: AuthRequest, res: Response) => {
  try {
    await prisma.load.update({ where: { id: req.params.id }, data: { status: 'CANCELLED' } });
    return res.json({ success: true, message: 'Load cancelled' });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

export { router as loadsRouter };
