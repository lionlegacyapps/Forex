import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

async function main() {
  console.log('🌱 Seeding database...');

  // Create tenants
  const tenant1 = await prisma.tenant.upsert({
    where: { id: 'tenant-alpha-logistics' },
    update: {},
    create: {
      id: 'tenant-alpha-logistics',
      name: 'Alpha Logistics LLC',
      dotNumber: '1234567',
      mcNumber: 'MC-789012',
      address: '1500 Commerce Dr, Dallas, TX 75201',
      phone: '214-555-0100',
      email: 'dispatch@alphalogistics.com',
      operationType: 'LONGHAUL',
    },
  });

  const tenant2 = await prisma.tenant.upsert({
    where: { id: 'tenant-swift-local' },
    update: {},
    create: {
      id: 'tenant-swift-local',
      name: 'Swift Local Delivery Co',
      dotNumber: '7654321',
      mcNumber: 'MC-345678',
      address: '800 Industrial Blvd, Atlanta, GA 30309',
      phone: '404-555-0200',
      email: 'dispatch@swiftlocal.com',
      operationType: 'LOCAL',
    },
  });

  // Create super dispatcher user
  const hashedPassword = await bcrypt.hash('dispatch123', 12);

  await prisma.user.upsert({
    where: { email: 'admin@dispatch.com' },
    update: {},
    create: {
      email: 'admin@dispatch.com',
      password: hashedPassword,
      name: 'Alex Rodriguez',
      role: 'SUPER_DISPATCHER',
    },
  });

  await prisma.user.upsert({
    where: { email: 'dispatcher@alphalogistics.com' },
    update: {},
    create: {
      email: 'dispatcher@alphalogistics.com',
      password: hashedPassword,
      name: 'Maria Santos',
      role: 'DISPATCHER',
      tenantId: tenant1.id,
    },
  });

  await prisma.user.upsert({
    where: { email: 'dispatcher@swiftlocal.com' },
    update: {},
    create: {
      email: 'dispatcher@swiftlocal.com',
      password: hashedPassword,
      name: 'James Cooper',
      role: 'DISPATCHER',
      tenantId: tenant2.id,
    },
  });

  // Alpha Logistics drivers (long-haul)
  const alphaDrivers = [
    {
      id: 'driver-alpha-1',
      name: 'Carlos Martinez',
      phone: '214-555-1001',
      cdlNumber: 'TX-CDL-001234',
      cdlState: 'TX',
      status: 'AVAILABLE',
      currentLat: 32.7767,
      currentLng: -96.797,
      currentCity: 'Dallas',
      currentState: 'TX',
      hosDriveRemaining: 9.5,
      hosShiftRemaining: 12.0,
      hosCycleRemaining: 65.0,
      equipmentTypes: 'DRY_VAN,REEFER',
      truckNumber: 'T-101',
      eldProvider: 'SAMSARA',
      eldDriverId: 'sam-drv-001',
      totalMiles: 187500,
      totalLoads: 342,
      rating: 4.9,
    },
    {
      id: 'driver-alpha-2',
      name: 'David Johnson',
      phone: '214-555-1002',
      cdlNumber: 'TX-CDL-005678',
      cdlState: 'TX',
      status: 'DRIVING',
      currentLat: 34.0522,
      currentLng: -118.2437,
      currentCity: 'Los Angeles',
      currentState: 'CA',
      hosDriveRemaining: 4.5,
      hosShiftRemaining: 6.0,
      hosCycleRemaining: 42.0,
      equipmentTypes: 'DRY_VAN',
      truckNumber: 'T-102',
      eldProvider: 'MOTIVE',
      eldDriverId: 'mot-drv-002',
      totalMiles: 225000,
      totalLoads: 415,
      rating: 4.7,
    },
    {
      id: 'driver-alpha-3',
      name: 'Sarah Williams',
      phone: '214-555-1003',
      cdlNumber: 'TX-CDL-009012',
      cdlState: 'TX',
      status: 'OFF_DUTY',
      currentLat: 33.4484,
      currentLng: -112.074,
      currentCity: 'Phoenix',
      currentState: 'AZ',
      hosDriveRemaining: 11.0,
      hosShiftRemaining: 14.0,
      hosCycleRemaining: 70.0,
      equipmentTypes: 'FLATBED,STEP_DECK',
      truckNumber: 'T-103',
      eldProvider: 'SAMSARA',
      eldDriverId: 'sam-drv-003',
      totalMiles: 95000,
      totalLoads: 180,
      rating: 4.8,
    },
    {
      id: 'driver-alpha-4',
      name: 'Mike Thompson',
      phone: '214-555-1004',
      cdlNumber: 'TX-CDL-003456',
      cdlState: 'TX',
      status: 'AVAILABLE',
      currentLat: 29.7604,
      currentLng: -95.3698,
      currentCity: 'Houston',
      currentState: 'TX',
      hosDriveRemaining: 11.0,
      hosShiftRemaining: 14.0,
      hosCycleRemaining: 68.0,
      equipmentTypes: 'REEFER',
      truckNumber: 'T-104',
      eldProvider: 'GEOTAB',
      eldDriverId: 'geo-drv-004',
      totalMiles: 143000,
      totalLoads: 267,
      rating: 4.6,
    },
    {
      id: 'driver-alpha-5',
      name: 'Jennifer Davis',
      phone: '214-555-1005',
      cdlNumber: 'TX-CDL-007890',
      cdlState: 'TX',
      status: 'ON_DUTY',
      currentLat: 41.8781,
      currentLng: -87.6298,
      currentCity: 'Chicago',
      currentState: 'IL',
      hosDriveRemaining: 8.0,
      hosShiftRemaining: 11.0,
      hosCycleRemaining: 55.0,
      equipmentTypes: 'DRY_VAN,INTERMODAL',
      truckNumber: 'T-105',
      eldProvider: 'MOTIVE',
      eldDriverId: 'mot-drv-005',
      totalMiles: 310000,
      totalLoads: 580,
      rating: 4.95,
    },
  ];

  for (const d of alphaDrivers) {
    await prisma.driver.upsert({
      where: { id: d.id },
      update: {},
      create: {
        ...d,
        tenantId: tenant1.id,
        cdlClass: 'A',
        cdlExpiry: new Date('2026-12-31'),
      },
    });
  }

  // Swift Local drivers
  const swiftDrivers = [
    {
      id: 'driver-swift-1',
      name: 'Robert Brown',
      phone: '404-555-2001',
      cdlNumber: 'GA-CDL-001122',
      cdlState: 'GA',
      status: 'AVAILABLE',
      currentLat: 33.749,
      currentLng: -84.388,
      currentCity: 'Atlanta',
      currentState: 'GA',
      hosDriveRemaining: 10.0,
      hosShiftRemaining: 13.0,
      hosCycleRemaining: 60.0,
      equipmentTypes: 'DRY_VAN,HOTSHOT',
      truckNumber: 'S-201',
      eldProvider: 'SAMSARA',
      eldDriverId: 'sam-drv-201',
      totalMiles: 75000,
      totalLoads: 420,
      rating: 4.8,
    },
    {
      id: 'driver-swift-2',
      name: 'Lisa Anderson',
      phone: '404-555-2002',
      cdlNumber: 'GA-CDL-003344',
      cdlState: 'GA',
      status: 'DRIVING',
      currentLat: 33.45,
      currentLng: -84.15,
      currentCity: 'Jonesboro',
      currentState: 'GA',
      hosDriveRemaining: 6.5,
      hosShiftRemaining: 9.0,
      hosCycleRemaining: 48.0,
      equipmentTypes: 'DRY_VAN',
      truckNumber: 'S-202',
      eldProvider: 'MOTIVE',
      eldDriverId: 'mot-drv-202',
      totalMiles: 52000,
      totalLoads: 310,
      rating: 4.7,
    },
    {
      id: 'driver-swift-3',
      name: 'Kevin Wilson',
      phone: '404-555-2003',
      cdlNumber: 'GA-CDL-005566',
      cdlState: 'GA',
      status: 'AVAILABLE',
      currentLat: 33.85,
      currentLng: -84.45,
      currentCity: 'Marietta',
      currentState: 'GA',
      hosDriveRemaining: 11.0,
      hosShiftRemaining: 14.0,
      hosCycleRemaining: 70.0,
      equipmentTypes: 'DRY_VAN,POWER_ONLY',
      truckNumber: 'S-203',
      eldProvider: 'NONE',
      totalMiles: 38000,
      totalLoads: 215,
      rating: 4.5,
    },
    {
      id: 'driver-swift-4',
      name: 'Patricia Taylor',
      phone: '404-555-2004',
      cdlNumber: 'GA-CDL-007788',
      cdlState: 'GA',
      status: 'OFF_DUTY',
      currentLat: 33.65,
      currentLng: -84.42,
      currentCity: 'College Park',
      currentState: 'GA',
      hosDriveRemaining: 11.0,
      hosShiftRemaining: 14.0,
      hosCycleRemaining: 70.0,
      equipmentTypes: 'DRY_VAN',
      truckNumber: 'S-204',
      eldProvider: 'SAMSARA',
      eldDriverId: 'sam-drv-204',
      totalMiles: 29000,
      totalLoads: 175,
      rating: 4.6,
    },
    {
      id: 'driver-swift-5',
      name: 'Thomas Jackson',
      phone: '404-555-2005',
      cdlNumber: 'GA-CDL-009900',
      cdlState: 'GA',
      status: 'AVAILABLE',
      currentLat: 33.95,
      currentLng: -84.0,
      currentCity: 'Lawrenceville',
      currentState: 'GA',
      hosDriveRemaining: 9.5,
      hosShiftRemaining: 12.5,
      hosCycleRemaining: 58.0,
      equipmentTypes: 'DRY_VAN,FLATBED',
      truckNumber: 'S-205',
      eldProvider: 'MOTIVE',
      eldDriverId: 'mot-drv-205',
      totalMiles: 44000,
      totalLoads: 260,
      rating: 4.75,
    },
  ];

  for (const d of swiftDrivers) {
    await prisma.driver.upsert({
      where: { id: d.id },
      update: {},
      create: {
        ...d,
        tenantId: tenant2.id,
        cdlClass: 'A',
        cdlExpiry: new Date('2027-06-30'),
      },
    });
  }

  // Sample loads for Alpha Logistics
  const alphaLoads = [
    {
      id: 'load-alpha-001',
      loadNumber: 'AL-2024-001',
      status: 'IN_TRANSIT',
      equipmentType: 'DRY_VAN',
      driverId: 'driver-alpha-2',
      commodity: 'Electronics',
      weight: 32000,
      pieces: 48,
      miles: 1480,
      rate: 3200,
      driverPay: 2240,
      fuelSurcharge: 320,
      brokerName: 'CH Robinson',
      brokerPhone: '800-323-7587',
      brokerEmail: 'loads@chrobinson.com',
      brokerMCNumber: 'MC-152134',
      referenceNumber: 'CHR-789456',
    },
    {
      id: 'load-alpha-002',
      loadNumber: 'AL-2024-002',
      status: 'AVAILABLE',
      equipmentType: 'REEFER',
      commodity: 'Frozen Food',
      weight: 44000,
      miles: 890,
      rate: 2850,
      driverPay: 1995,
      fuelSurcharge: 285,
      brokerName: 'Echo Global',
      brokerPhone: '800-354-7993',
      brokerEmail: 'ops@echo.com',
      brokerMCNumber: 'MC-430170',
      referenceNumber: 'ECH-456123',
      tempMin: 0,
      tempMax: 32,
    },
    {
      id: 'load-alpha-003',
      loadNumber: 'AL-2024-003',
      status: 'ASSIGNED',
      equipmentType: 'FLATBED',
      driverId: 'driver-alpha-3',
      commodity: 'Steel Coils',
      weight: 48000,
      miles: 720,
      rate: 2400,
      driverPay: 1680,
      fuelSurcharge: 240,
      brokerName: 'Coyote Logistics',
      brokerPhone: '888-461-7100',
      brokerMCNumber: 'MC-388481',
      referenceNumber: 'COY-321789',
      hazmat: false,
    },
    {
      id: 'load-alpha-004',
      loadNumber: 'AL-2024-004',
      status: 'AVAILABLE',
      equipmentType: 'DRY_VAN',
      commodity: 'Paper Products',
      weight: 38000,
      miles: 1200,
      rate: 2900,
      driverPay: 2030,
      fuelSurcharge: 290,
      brokerName: 'Transplace',
      brokerPhone: '888-445-1789',
      brokerMCNumber: 'MC-500290',
      referenceNumber: 'TRP-654987',
    },
    {
      id: 'load-alpha-005',
      loadNumber: 'AL-2024-005',
      status: 'DELIVERED',
      equipmentType: 'DRY_VAN',
      driverId: 'driver-alpha-1',
      commodity: 'Automotive Parts',
      weight: 25000,
      miles: 600,
      rate: 1800,
      driverPay: 1260,
      fuelSurcharge: 180,
      brokerName: 'XPO Logistics',
      brokerPhone: '800-755-2728',
      brokerMCNumber: 'MC-273634',
      referenceNumber: 'XPO-112233',
    },
  ];

  for (const l of alphaLoads) {
    const existing = await prisma.load.findUnique({ where: { id: l.id } });
    if (!existing) {
      const load = await prisma.load.create({
        data: {
          ...l,
          tenantId: tenant1.id,
          deliveredAt: l.status === 'DELIVERED' ? new Date(Date.now() - 3600000) : undefined,
          pickedUpAt: l.status === 'IN_TRANSIT' || l.status === 'DELIVERED' ? new Date(Date.now() - 86400000) : undefined,
        },
      });

      // Create stops
      await prisma.loadStop.createMany({
        data: getStopsForLoad(load.id, l.loadNumber),
      });
    }
  }

  // Sample loads for Swift Local
  const swiftLoads = [
    {
      id: 'load-swift-001',
      loadNumber: 'SL-2024-001',
      status: 'AVAILABLE',
      equipmentType: 'DRY_VAN',
      commodity: 'General Merchandise',
      weight: 15000,
      miles: 120,
      rate: 650,
      driverPay: 455,
      fuelSurcharge: 65,
      brokerName: 'Amazon Freight',
      brokerPhone: '866-311-7588',
      referenceNumber: 'AMZ-987654',
    },
    {
      id: 'load-swift-002',
      loadNumber: 'SL-2024-002',
      status: 'DRIVING',
      equipmentType: 'HOTSHOT',
      driverId: 'driver-swift-2',
      commodity: 'Machine Parts',
      weight: 8000,
      miles: 85,
      rate: 450,
      driverPay: 315,
      fuelSurcharge: 45,
      brokerName: 'Uber Freight',
      referenceNumber: 'UBR-246810',
    },
    {
      id: 'load-swift-003',
      loadNumber: 'SL-2024-003',
      status: 'AVAILABLE',
      equipmentType: 'DRY_VAN',
      commodity: 'Home Appliances',
      weight: 18000,
      miles: 95,
      rate: 520,
      driverPay: 364,
      fuelSurcharge: 52,
      brokerName: 'Home Depot Logistics',
      referenceNumber: 'HD-135791',
    },
    {
      id: 'load-swift-004',
      loadNumber: 'SL-2024-004',
      status: 'ASSIGNED',
      equipmentType: 'DRY_VAN',
      driverId: 'driver-swift-1',
      commodity: 'Clothing',
      weight: 12000,
      miles: 145,
      rate: 720,
      driverPay: 504,
      fuelSurcharge: 72,
      brokerName: 'FedEx Freight',
      referenceNumber: 'FX-864200',
    },
    {
      id: 'load-swift-005',
      loadNumber: 'SL-2024-005',
      status: 'DELIVERED',
      equipmentType: 'DRY_VAN',
      driverId: 'driver-swift-3',
      commodity: 'Food & Beverage',
      weight: 22000,
      miles: 60,
      rate: 380,
      driverPay: 266,
      fuelSurcharge: 38,
      brokerName: 'Walmart Logistics',
      referenceNumber: 'WMT-753951',
    },
  ];

  for (const l of swiftLoads) {
    const existing = await prisma.load.findUnique({ where: { id: l.id } });
    if (!existing) {
      const load = await prisma.load.create({
        data: {
          ...l,
          tenantId: tenant2.id,
          status: l.status === 'DRIVING' ? 'IN_TRANSIT' : l.status,
          deliveredAt: l.status === 'DELIVERED' ? new Date(Date.now() - 7200000) : undefined,
          pickedUpAt: l.status === 'DRIVING' || l.status === 'DELIVERED' ? new Date(Date.now() - 14400000) : undefined,
        },
      });
      await prisma.loadStop.createMany({
        data: getStopsForLoad(load.id, l.loadNumber),
      });
    }
  }

  // Sample alerts (check count before inserting to avoid duplicates on re-seed)
  const alertCount = await prisma.alert.count();
  if (alertCount === 0) {
    await prisma.alert.createMany({
      data: [
        {
          type: 'WARNING',
          title: 'HOS Near Limit',
          message: 'Driver David Johnson has only 4.5 hours of drive time remaining',
          tenantId: tenant1.id,
          driverId: 'driver-alpha-2',
          isRead: false,
        },
        {
          type: 'INFO',
          title: 'Load Delivered',
          message: 'Load AL-2024-005 delivered successfully by Carlos Martinez',
          tenantId: tenant1.id,
          loadId: 'load-alpha-005',
          isRead: false,
        },
        {
          type: 'WARNING',
          title: 'Weather Alert',
          message: 'Winter storm warning along I-40 corridor in AZ/NM — check routes',
          isRead: false,
        },
      ],
    });
  }

  console.log('✅ Seed complete!');
  console.log('');
  console.log('Login credentials:');
  console.log('  Super Dispatcher: admin@dispatch.com / dispatch123');
  console.log('  Alpha Dispatcher: dispatcher@alphalogistics.com / dispatch123');
  console.log('  Swift Dispatcher: dispatcher@swiftlocal.com / dispatch123');
}

function getStopsForLoad(loadId: string, loadNumber: string) {
  const stopData: Record<string, { pickup: { city: string; state: string; address: string }; delivery: { city: string; state: string; address: string } }> = {
    'AL-2024-001': { pickup: { city: 'Dallas', state: 'TX', address: '2300 Irving Blvd' }, delivery: { city: 'Los Angeles', state: 'CA', address: '1800 E Olympic Blvd' } },
    'AL-2024-002': { pickup: { city: 'Chicago', state: 'IL', address: '1900 W Pershing Rd' }, delivery: { city: 'Nashville', state: 'TN', address: '500 Cowan St' } },
    'AL-2024-003': { pickup: { city: 'Pittsburgh', state: 'PA', address: '100 Technology Dr' }, delivery: { city: 'Columbus', state: 'OH', address: '800 Linden Ave' } },
    'AL-2024-004': { pickup: { city: 'Memphis', state: 'TN', address: '3900 Lamar Ave' }, delivery: { city: 'Atlanta', state: 'GA', address: '1600 Airport Rd' } },
    'AL-2024-005': { pickup: { city: 'Detroit', state: 'MI', address: '12000 Mound Rd' }, delivery: { city: 'Indianapolis', state: 'IN', address: '3600 E 38th St' } },
    'SL-2024-001': { pickup: { city: 'Atlanta', state: 'GA', address: '200 Distribution Way' }, delivery: { city: 'Athens', state: 'GA', address: '100 Commerce Blvd' } },
    'SL-2024-002': { pickup: { city: 'Marietta', state: 'GA', address: '50 Industrial Pkwy' }, delivery: { city: 'Peachtree City', state: 'GA', address: '300 Hwy 54' } },
    'SL-2024-003': { pickup: { city: 'Kennesaw', state: 'GA', address: '75 Big Shanty Rd' }, delivery: { city: 'Smyrna', state: 'GA', address: '2400 Atlanta Rd' } },
    'SL-2024-004': { pickup: { city: 'Atlanta', state: 'GA', address: '1000 Northside Dr' }, delivery: { city: 'Savannah', state: 'GA', address: '500 Export Blvd' } },
    'SL-2024-005': { pickup: { city: 'Tucker', state: 'GA', address: '4000 Lawrenceville Hwy' }, delivery: { city: 'Decatur', state: 'GA', address: '600 Church St' } },
  };

  const s = stopData[loadNumber] || {
    pickup: { city: 'Origin City', state: 'TX', address: '100 Pickup Ln' },
    delivery: { city: 'Dest City', state: 'CA', address: '200 Delivery Ave' },
  };

  const now = new Date();
  return [
    {
      loadId,
      type: 'PICKUP',
      sequence: 1,
      address: s.pickup.address,
      city: s.pickup.city,
      state: s.pickup.state,
      zip: '00000',
      scheduledArrival: new Date(now.getTime() + 2 * 3600000),
    },
    {
      loadId,
      type: 'DELIVERY',
      sequence: 2,
      address: s.delivery.address,
      city: s.delivery.city,
      state: s.delivery.state,
      zip: '00000',
      scheduledArrival: new Date(now.getTime() + 26 * 3600000),
    },
  ];
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
