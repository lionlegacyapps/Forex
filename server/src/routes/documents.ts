import { Router, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import { authenticate, AuthRequest, resolveTenant } from '../middleware/auth';

const router = Router();
const prisma = new PrismaClient();

const uploadDir = path.join(__dirname, '../../uploads');
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });

const storage = multer.diskStorage({
  destination: uploadDir,
  filename: (_req, file, cb) => {
    cb(null, `${Date.now()}-${file.originalname.replace(/\s/g, '_')}`);
  },
});

const upload = multer({ storage, limits: { fileSize: 20 * 1024 * 1024 } });

router.use(authenticate);

router.get('/', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const where: Record<string, unknown> = {};
    if (tenantId) where.tenantId = tenantId;
    if (req.query.loadId) where.loadId = req.query.loadId;
    if (req.query.type) where.type = req.query.type;

    const docs = await prisma.document.findMany({
      where,
      include: { load: { select: { loadNumber: true } } },
      orderBy: { createdAt: 'desc' },
    });

    return res.json({ success: true, data: docs });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.post('/upload', upload.single('file'), async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req) || req.body.tenantId;
    if (!tenantId) return res.status(400).json({ success: false, error: 'tenantId required' });
    if (!req.file) return res.status(400).json({ success: false, error: 'No file uploaded' });

    const { type, loadId, driverId } = req.body;

    const doc = await prisma.document.create({
      data: {
        tenantId,
        loadId: loadId || undefined,
        driverId: driverId || undefined,
        type: type || 'OTHER',
        fileName: req.file.originalname,
        fileUrl: `/uploads/${req.file.filename}`,
        parseStatus: 'PROCESSING',
      },
    });

    // Simulate async parsing
    setTimeout(async () => {
      const mockParsed = parseMockDocument(type, req.file!.originalname);
      await prisma.document.update({
        where: { id: doc.id },
        data: {
          parsedData: JSON.stringify(mockParsed),
          parseStatus: 'DONE',
        },
      });
    }, 2000);

    return res.status(201).json({ success: true, data: doc });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.get('/:id', async (req: AuthRequest, res: Response) => {
  try {
    const doc = await prisma.document.findUnique({ where: { id: req.params.id }, include: { load: true } });
    if (!doc) return res.status(404).json({ success: false, error: 'Document not found' });
    return res.json({ success: true, data: { ...doc, parsedData: doc.parsedData ? JSON.parse(doc.parsedData) : null } });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

router.delete('/:id', async (req: AuthRequest, res: Response) => {
  try {
    const doc = await prisma.document.findUnique({ where: { id: req.params.id } });
    if (!doc) return res.status(404).json({ success: false, error: 'Not found' });

    const filePath = path.join(uploadDir, path.basename(doc.fileUrl));
    if (fs.existsSync(filePath)) fs.unlinkSync(filePath);

    await prisma.document.delete({ where: { id: req.params.id } });
    return res.json({ success: true });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

function parseMockDocument(type: string, filename: string) {
  if (type === 'RATE_CONFIRMATION') {
    return {
      loadNumber: `RC-${Math.floor(Math.random() * 100000)}`,
      broker: 'CH Robinson',
      brokerMC: 'MC-152134',
      origin: { city: 'Dallas', state: 'TX', address: '2300 Irving Blvd', zip: '75207' },
      destination: { city: 'Los Angeles', state: 'CA', address: '1800 E Olympic Blvd', zip: '90021' },
      pickupDate: new Date(Date.now() + 86400000).toISOString(),
      deliveryDate: new Date(Date.now() + 172800000).toISOString(),
      commodity: 'Electronics',
      weight: 32000,
      rate: 3200,
      fuelSurcharge: 320,
      equipmentType: 'DRY_VAN',
      contactName: 'Sarah Miller',
      contactPhone: '800-323-7587',
      contactEmail: 'smiller@chrobinson.com',
    };
  } else if (type === 'BOL') {
    return {
      bolNumber: `BOL-${Math.floor(Math.random() * 100000)}`,
      shipper: { name: 'Electronics Corp', address: '2300 Irving Blvd, Dallas, TX 75207' },
      consignee: { name: 'Distribution Center West', address: '1800 E Olympic Blvd, Los Angeles, CA 90021' },
      items: [{ description: 'Electronics - Computers', pieces: 48, weight: 32000, class: '85' }],
      poNumber: `PO-${Math.floor(Math.random() * 10000)}`,
      specialInstructions: 'Fragile - Handle with care',
      signedAt: new Date().toISOString(),
    };
  } else if (type === 'POD') {
    return {
      signedBy: 'John Receiver',
      signedAt: new Date().toISOString(),
      deliveryLocation: '1800 E Olympic Blvd, Los Angeles, CA 90021',
      pieces: 48,
      condition: 'Good',
      notes: 'Delivered in full, no exceptions',
    };
  }
  return { fileName: filename, parsedAt: new Date().toISOString() };
}

export { router as documentsRouter };
