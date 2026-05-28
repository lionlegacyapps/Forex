# TruckDispatch AI — Advanced Multi-Tenant Dispatch Platform

A production-ready AI-powered truck dispatching application with multi-tenant support, real-time fleet tracking, and intelligent load matching.

## Quick Start

```bash
# Install all dependencies
npm install

# Setup database and seed data
npm run setup

# Start both server and client
npm run dev
```

**Server:** http://localhost:3001  
**Client:** http://localhost:5173

## Demo Login Credentials (password: `dispatch123`)

| Account | Email | Access |
|---|---|---|
| Super Dispatcher | admin@dispatch.com | Full access — all companies |
| Alpha Logistics | dispatcher@alphalogistics.com | Long-haul fleet |
| Swift Local | dispatcher@swiftlocal.com | Local delivery fleet |

## Architecture

```
/
├── client/          # React 18 + TypeScript + Vite + TailwindCSS
├── server/          # Node.js + Express + TypeScript + Prisma
└── shared/          # Shared TypeScript types
```

### Multi-Tenant Design
- Each tenant = a trucking company you dispatch for
- `tenantId` isolation on every database query
- Super Dispatcher can view/switch between all companies
- Regular dispatchers see only their company's data
- JWT-based auth with 15-minute access tokens + 7-day refresh token rotation

### Scale Architecture
```
CDN (Cloudflare)
    └── React SPA (static assets)
         │
Load Balancer
    └── Express API Pods (stateless JWT — horizontal scale)
         ├── PostgreSQL (primary + read replicas)
         ├── Redis Cluster (cache + Bull job queue)
         └── S3 (document storage)
```

## Features

### Core Dispatch
- **Dashboard** — Live fleet map, KPI stats, revenue charts, HOS driver table
- **Dispatch Board** — Kanban view: Available → Assigned → In Transit → Delivered
- **Load Management** — Full CRUD, multi-stop routing, broker info, rate tracking
- **Driver Management** — CDL tracking, HOS progress bars, ELD status, equipment
- **Load Board** — DAT/Truckstop integration with one-click import

### AI Features (DeepSeek LLM)
- **AI Assistant** — Chat for load matching, rate negotiation, HOS compliance checks
- **Load Matching** — Scores drivers by location, HOS hours, equipment, history
- **Rate Calculator** — Market rate analysis with min/max/suggested/per-mile
- **Document Parser** — Auto-extracts structured data from BOLs, Rate Cons, PODs

### Integrations (mock-ready structure)
- **ELD**: Motive, Samsara, Geotab — HOS sync, location tracking
- **Maps**: Mapbox (rendering), HERE (truck routing), Google Places (autocomplete)
- **Communications**: Telnyx (SMS/voice), LiveKit (video dispatch calls)
- **Weather**: OpenWeatherMap route alerts
- **Automation**: Playwright load board scraping

## Environment Variables

Copy `.env.example` to `.env`:

```bash
DEEPSEEK_API_KEY=        # AI features (mock fallback if missing)
VITE_MAPBOX_TOKEN=       # Live map (placeholder map if missing)
TELNYX_API_KEY=          # SMS to drivers (logged to console if missing)
SAMSARA_API_KEY=         # ELD sync
MOTIVE_API_KEY=          # ELD sync
```

The app runs fully functional in demo mode without any API keys.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| State | Zustand + TanStack Query |
| Charts | Recharts |
| Maps | Mapbox GL JS |
| Backend | Node.js, Express, TypeScript |
| Database | SQLite (dev) / PostgreSQL (prod) — Prisma ORM |
| Auth | JWT + bcrypt, refresh token rotation |
| AI | DeepSeek API with graceful mock fallback |
