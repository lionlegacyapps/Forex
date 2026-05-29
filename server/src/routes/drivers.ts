import { Router, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { authenticate, AuthRequest, resolveTenant } from '../middleware/auth';

const router = Router();
const prisma = new PrismaClient();

router.use(authenticate);

router.get('/', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const { status, equipment } = req.query;

    const where: Record<string, unknown> = { isActive: true };
    if (tenantId) where.tenantId = tenantId;
    if (status) where.status = status;
    if (equipment) where.equipmentTypes = { contains: equipment as string };

    const drivers = await prisma.driver.findMany({
      where,
      include: { tenant: { select: { id: true, name: true } } },
      orderBy: { name: 'asc' },
    });

    const mapped = drivers.map((d) => ({
      ...d,
      equipmentType: d.equipmentTypes.split(',').filter(Boolean),
    }));

    return res.json({ success: true, data: mapped });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.get('/:id', async (req: AuthRequest, res: Response) => {
  try {
    const driver = await prisma.driver.findUnique({
      where: { id: req.params.id },
      include: {
        tenant: true,
        loads: { take: 10, orderBy: { createdAt: 'desc' }, include: { stops: true } },
      },
    });
    if (!driver) return res.status(404).json({ success: false, error: 'Driver not found' });
    return res.json({ success: true, data: { ...driver, equipmentType: driver.equipmentTypes.split(',').filter(Boolean) } });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.post('/', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req) || req.body.tenantId;
    if (!tenantId) return res.status(400).json({ success: false, error: 'tenantId required' });

    const { name, email, phone, cdlNumber, cdlState, cdlClass, cdlExpiry, equipmentType, truckNumber, trailerNumber, eldProvider, eldDriverId } = req.body;

    const driver = await prisma.driver.create({
      data: {
        tenantId,
        name,
        email,
        phone,
        cdlNumber,
        cdlState,
        cdlClass: cdlClass || 'A',
        cdlExpiry: new Date(cdlExpiry),
        equipmentTypes: Array.isArray(equipmentType) ? equipmentType.join(',') : equipmentType,
        truckNumber,
        trailerNumber,
        eldProvider,
        eldDriverId,
      },
    });
    return res.status(201).json({ success: true, data: { ...driver, equipmentType: driver.equipmentTypes.split(',') } });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.put('/:id', async (req: AuthRequest, res: Response) => {
  try {
    const { name, email, phone, cdlNumber, cdlState, cdlClass, cdlExpiry, status, equipmentType, truckNumber, trailerNumber, eldProvider, eldDriverId, currentLat, currentLng, currentCity, currentState, hosDriveRemaining, hosShiftRemaining, hosCycleRemaining } = req.body;

    const driver = await prisma.driver.update({
      where: { id: req.params.id },
      data: {
        name,
        email,
        phone,
        cdlNumber,
        cdlState,
        cdlClass,
        cdlExpiry: cdlExpiry ? new Date(cdlExpiry) : undefined,
        status,
        equipmentTypes: Array.isArray(equipmentType) ? equipmentType.join(',') : equipmentType,
        truckNumber,
        trailerNumber,
        eldProvider,
        eldDriverId,
        currentLat,
        currentLng,
        currentCity,
        currentState,
        hosDriveRemaining,
        hosShiftRemaining,
        hosCycleRemaining,
      },
    });
    return res.json({ success: true, data: { ...driver, equipmentType: driver.equipmentTypes.split(',') } });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.delete('/:id', async (req: AuthRequest, res: Response) => {
  try {
    await prisma.driver.update({ where: { id: req.params.id }, data: { isActive: false } });
    return res.json({ success: true, message: 'Driver deactivated' });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

// Update driver location (from ELD webhook or mobile app)
router.post('/:id/location', async (req: AuthRequest, res: Response) => {
  try {
    const { lat, lng, city, state, speed } = req.body;
    const driver = await prisma.driver.update({
      where: { id: req.params.id },
      data: { currentLat: lat, currentLng: lng, currentCity: city, currentState: state },
    });
    return res.json({ success: true, data: { lat: driver.currentLat, lng: driver.currentLng } });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

export { router as driversRouter };
