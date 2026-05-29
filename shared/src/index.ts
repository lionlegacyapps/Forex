// ── Tenant / Company ──────────────────────────────────────────────────────────
export interface Tenant {
  id: string;
  name: string;
  dotNumber?: string;
  mcNumber?: string;
  address?: string;
  phone?: string;
  email?: string;
  operationType: 'LOCAL' | 'REGIONAL' | 'LONGHAUL' | 'MIXED';
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

// ── User / Auth ───────────────────────────────────────────────────────────────
export type UserRole = 'SUPER_DISPATCHER' | 'DISPATCHER' | 'DRIVER' | 'COMPANY_ADMIN';

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  tenantId?: string;
  tenant?: Tenant;
  isActive: boolean;
  createdAt: string;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

// ── Driver ────────────────────────────────────────────────────────────────────
export type DriverStatus = 'AVAILABLE' | 'ON_DUTY' | 'DRIVING' | 'OFF_DUTY' | 'SLEEPER';

export interface Driver {
  id: string;
  tenantId: string;
  tenant?: Tenant;
  name: string;
  email?: string;
  phone: string;
  cdlNumber: string;
  cdlState: string;
  cdlClass: 'A' | 'B' | 'C';
  cdlExpiry: string;
  status: DriverStatus;
  currentLat?: number;
  currentLng?: number;
  currentCity?: string;
  currentState?: string;
  hosDriveRemaining: number;
  hosShiftRemaining: number;
  hosCycleRemaining: number;
  equipmentType: string[];
  truckNumber?: string;
  trailerNumber?: string;
  eldProvider?: 'MOTIVE' | 'SAMSARA' | 'GEOTAB' | 'NONE';
  eldDriverId?: string;
  totalMiles: number;
  totalLoads: number;
  rating: number;
  isActive: boolean;
  createdAt: string;
}

// ── Load ──────────────────────────────────────────────────────────────────────
export type LoadStatus =
  | 'AVAILABLE'
  | 'ASSIGNED'
  | 'IN_TRANSIT'
  | 'AT_PICKUP'
  | 'AT_DELIVERY'
  | 'DELIVERED'
  | 'CANCELLED';

export type EquipmentType =
  | 'DRY_VAN'
  | 'REEFER'
  | 'FLATBED'
  | 'STEP_DECK'
  | 'RGN'
  | 'TANKER'
  | 'INTERMODAL'
  | 'HOTSHOT'
  | 'POWER_ONLY';

export interface LoadStop {
  id: string;
  loadId: string;
  type: 'PICKUP' | 'DELIVERY' | 'LAYOVER';
  sequence: number;
  address: string;
  city: string;
  state: string;
  zip: string;
  lat?: number;
  lng?: number;
  scheduledArrival: string;
  actualArrival?: string;
  scheduledDeparture?: string;
  actualDeparture?: string;
  contactName?: string;
  contactPhone?: string;
  notes?: string;
  referenceNumber?: string;
}

export interface Load {
  id: string;
  tenantId: string;
  tenant?: Tenant;
  loadNumber: string;
  status: LoadStatus;
  equipmentType: EquipmentType;
  driverId?: string;
  driver?: Driver;
  stops: LoadStop[];
  commodity: string;
  weight: number;
  pieces?: number;
  miles?: number;
  rate: number;
  driverPay?: number;
  fuelSurcharge?: number;
  brokerName?: string;
  brokerPhone?: string;
  brokerEmail?: string;
  brokerMCNumber?: string;
  referenceNumber?: string;
  poNumber?: string;
  specialInstructions?: string;
  hazmat: boolean;
  teamLoad: boolean;
  tempMin?: number;
  tempMax?: number;
  createdAt: string;
  updatedAt: string;
  pickedUpAt?: string;
  deliveredAt?: string;
}

// ── Document ──────────────────────────────────────────────────────────────────
export type DocumentType = 'BOL' | 'RATE_CONFIRMATION' | 'POD' | 'INVOICE' | 'OTHER';

export interface Document {
  id: string;
  tenantId: string;
  loadId?: string;
  load?: Load;
  type: DocumentType;
  fileName: string;
  fileUrl: string;
  parsedData?: Record<string, unknown>;
  parseStatus: 'PENDING' | 'PROCESSING' | 'DONE' | 'FAILED';
  createdAt: string;
}

// ── AI Chat ───────────────────────────────────────────────────────────────────
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface AILoadMatchResult {
  driverId: string;
  driver: Driver;
  score: number;
  reasons: string[];
  estimatedPickupTime: string;
  distanceToPickup: number;
}

export interface AIRateResult {
  suggestedRate: number;
  minRate: number;
  maxRate: number;
  marketRate: number;
  ratePerMile: number;
  confidence: number;
  factors: string[];
}

// ── Integration ───────────────────────────────────────────────────────────────
export interface ELDUpdate {
  driverId: string;
  eldDriverId: string;
  provider: string;
  lat: number;
  lng: number;
  speed: number;
  hosDriveRemaining: number;
  hosShiftRemaining: number;
  hosCycleRemaining: number;
  status: DriverStatus;
  updatedAt: string;
}

export interface WeatherAlert {
  severity: 'INFO' | 'WARNING' | 'SEVERE';
  type: string;
  description: string;
  affectedStates: string[];
  startTime: string;
  endTime: string;
}

export interface RouteInfo {
  distance: number;
  duration: number;
  polyline: string;
  tollCost?: number;
  fuelCost?: number;
  waypoints: { lat: number; lng: number; label: string }[];
  weatherAlerts: WeatherAlert[];
}

// ── API Responses ─────────────────────────────────────────────────────────────
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

// ── Dashboard Stats ───────────────────────────────────────────────────────────
export interface DashboardStats {
  activeLoads: number;
  availableDrivers: number;
  inTransitLoads: number;
  deliveredToday: number;
  revenueToday: number;
  revenueWeek: number;
  revenueMonth: number;
  avgRatePerMile: number;
  onTimeDeliveryRate: number;
  alerts: DashboardAlert[];
}

export interface DashboardAlert {
  id: string;
  type: 'WARNING' | 'INFO' | 'ERROR';
  title: string;
  message: string;
  tenantId?: string;
  tenantName?: string;
  driverId?: string;
  driverName?: string;
  loadId?: string;
  loadNumber?: string;
  createdAt: string;
}
