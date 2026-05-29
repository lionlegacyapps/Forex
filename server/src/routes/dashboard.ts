import { Router, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { authenticate, AuthRequest, resolveTenant } from '../middleware/auth';

const router = Router();
const prisma = new PrismaClient();

router.use(authenticate);

router.get('/stats', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const where: Record<string, unknown> = {};
    if (tenantId) where.tenantId = tenantId;

    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);

    const weekStart = new Date();
    weekStart.setDate(weekStart.getDate() - 7);

    const monthStart = new Date();
    monthStart.setDate(1);
    monthStart.setHours(0, 0, 0, 0);

    const [
      activeLoads,
      availableDrivers,
      inTransitLoads,
      deliveredToday,
      revenueToday,
      revenueWeek,
      revenueMonth,
      alerts,
    ] = await Promise.all([
      prisma.load.count({ where: { ...where, status: { in: ['ASSIGNED', 'IN_TRANSIT', 'AT_PICKUP', 'AT_DELIVERY'] } } }),
      prisma.driver.count({ where: { ...(tenantId ? { tenantId } : {}), status: 'AVAILABLE', isActive: true } }),
      prisma.load.count({ where: { ...where, status: { in: ['IN_TRANSIT', 'AT_PICKUP', 'AT_DELIVERY'] } } }),
      prisma.load.count({ where: { ...where, status: 'DELIVERED', deliveredAt: { gte: todayStart } } }),
      prisma.load.aggregate({ where: { ...where, status: 'DELIVERED', deliveredAt: { gte: todayStart } }, _sum: { rate: true } }),
      prisma.load.aggregate({ where: { ...where, status: 'DELIVERED', deliveredAt: { gte: weekStart } }, _sum: { rate: true } }),
      prisma.load.aggregate({ where: { ...where, status: 'DELIVERED', deliveredAt: { gte: monthStart } }, _sum: { rate: true } }),
      prisma.alert.findMany({ where: { ...(tenantId ? { tenantId } : {}), isRead: false }, take: 10, orderBy: { createdAt: 'desc' } }),
    ]);

    // Calculate avg rate per mile
    const loadsWithMiles = await prisma.load.findMany({
      where: { ...where, status: 'DELIVERED', miles: { gt: 0 }, deliveredAt: { gte: monthStart } },
      select: { rate: true, miles: true },
    });

    const avgRatePerMile = loadsWithMiles.length
      ? loadsWithMiles.reduce((acc, l) => acc + (l.rate / (l.miles || 1)), 0) / loadsWithMiles.length
      : 0;

    return res.json({
      success: true,
      data: {
        activeLoads,
        availableDrivers,
        inTransitLoads,
        deliveredToday,
        revenueToday: revenueToday._sum.rate || 0,
        revenueWeek: revenueWeek._sum.rate || 0,
        revenueMonth: revenueMonth._sum.rate || 0,
        avgRatePerMile: Math.round(avgRatePerMile * 100) / 100,
        onTimeDeliveryRate: 94.2, // mock for now
        alerts: alerts.map((a) => ({
          ...a,
          createdAt: a.createdAt.toISOString(),
        })),
      },
    });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.get('/map-data', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const driverWhere: Record<string, unknown> = { isActive: true, currentLat: { not: null } };
    if (tenantId) driverWhere.tenantId = tenantId;

    const drivers = await prisma.driver.findMany({
      where: driverWhere,
      include: { tenant: { select: { id: true, name: true } } },
      select: {
        id: true, name: true, status: true, truckNumber: true,
        currentLat: true, currentLng: true, currentCity: true, currentState: true,
        hosDriveRemaining: true, equipmentTypes: true,
        tenant: true,
      },
    });

    const loadWhere: Record<string, unknown> = { status: { in: ['ASSIGNED', 'IN_TRANSIT', 'AT_PICKUP', 'AT_DELIVERY'] } };
    if (tenantId) loadWhere.tenantId = tenantId;

    const loads = await prisma.load.findMany({
      where: loadWhere,
      include: {
        stops: { orderBy: { sequence: 'asc' } },
        driver: { select: { id: true, name: true, currentLat: true, currentLng: true } },
        tenant: { select: { id: true, name: true } },
      },
    });

    return res.json({ success: true, data: { drivers, loads } });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.get('/revenue-chart', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const where: Record<string, unknown> = { status: 'DELIVERED' };
    if (tenantId) where.tenantId = tenantId;

    // Last 30 days by day
    const result = [];
    for (let i = 29; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      date.setHours(0, 0, 0, 0);
      const nextDate = new Date(date);
      nextDate.setDate(nextDate.getDate() + 1);

      const agg = await prisma.load.aggregate({
        where: { ...where, deliveredAt: { gte: date, lt: nextDate } },
        _sum: { rate: true },
        _count: true,
      });

      result.push({
        date: date.toISOString().slice(0, 10),
        revenue: agg._sum.rate || 0,
        loads: agg._count,
      });
    }

    return res.json({ success: true, data: result });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

export { router as dashboardRouter };
