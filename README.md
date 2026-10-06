# Algorithmic Trading Platform — Backend

Private algorithmic trading platform backend. Persistent data targets
**Supabase PostgreSQL**. Designed to run on a generic Ubuntu VPS (no
Hostinger-specific dependencies).

---

## CURRENTLY IMPLEMENTED

- Modular FastAPI application skeleton
- `GET /health` liveness endpoint (does not require the database)
- `GET /health/database` connectivity probe (`SELECT 1`; no secrets in response)
- Environment-variable configuration (`pydantic-settings`, loads repo-root `.env`)
- Structured logging foundation
- Application exception hierarchy
- SQLAlchemy engine/session architecture for Supabase PostgreSQL via `DATABASE_URL`
  (psycopg3 driver, TLS for remote hosts; starts without `DATABASE_URL`)
- Alembic migration tooling wired from app settings
- Version 1 trading schema (models + migrations `111d98cf92b8` → `a86f3472f808`)
  with fail-closed defaults (PAPER + DISABLED), composite order/proposal account
  integrity, and defense-in-depth CHECK constraints
- Trading Safety Pipeline V1: TradeProposalService → RiskEngine → OrderValidator
  → BrokerRouter → SimulationBroker (PAPER only; zero real-broker network calls)
- Paper Execution & Portfolio Accounting V1: deterministic sim fills, positions,
  realized/unrealized P&L, exposure, daily PnL → Risk Engine feedback
- Market Data Provider V1: read-only MarketDataService + Alpaca data API provider
  (no order execution); SimulationMarketData preserved for offline tests
- Alpaca Paper Account Read-Path V1: read-only paper account/positions/orders via
  BrokerStateService; observational reconciliation; no order submission
- `scripts/check-database.sh` safe connectivity check
- Abstract `BrokerAdapter` contract and shared broker types
- Module boundaries for the future trading pipeline (logic not implemented)
- Docker + Docker Compose for the API service only
- pytest coverage (startup, health, config, schema)

## PLANNED (not implemented)

- Real broker order execution adapters (Alpaca paper/live execution, Tradovate, IBKR, …)
- Strategy orchestration and automated strategies
- Live trading modes / live execution
- Market memory, backtesting
- External signal ingestion (including Telegram/Discord)
- AI-generated trade proposals
- Frontend
- Public trade-execution HTTP API

---

## Architecture overview

Future automated order flow (module boundaries exist; logic does not):

```
Signal / Strategy
  → Strategy Orchestrator
  → Trade Proposal
  → Risk Engine
  → Order Validator
  → Broker Router
  → Broker Adapter
  → Broker API
```

**Safety rule:** strategies, AI models, and external signals must never
call a broker adapter directly. All orders go through the pipeline above.

### Project layout

```
backend/
  app/
    api/            # HTTP routes (health only for now)
    core/           # config, logging, exceptions, deps
    db/             # SQLAlchemy base + session
    models/         # ORM models (none yet)
    schemas/        # Pydantic request/response schemas
    services/       # application services (planned)
    brokers/
      base/         # BrokerAdapter ABC + shared types
      adapters/     # concrete providers (planned)
    trading/
      proposals/    # trade proposals (planned)
      risk/         # risk engine (planned)
      validation/   # order validator (planned)
      routing/      # broker router (planned)
      execution/    # execution (planned)
    strategies/     # strategy modules (planned)
    market_data/    # market data (planned)
    market_memory/  # market memory (planned)
    signals/        # external signals (planned)
    backtesting/    # backtesting (planned)
    audit/          # audit logging (planned)
  tests/
  migrations/       # Alembic
infra/              # future infra helpers
scripts/            # operational scripts
docs/               # additional documentation
```

---

## Environment configuration

1. Copy the example file:

```bash
cp .env.example .env
```

2. Set **`DATABASE_URL` in the repository-root `.env`** to your **Supabase**
   PostgreSQL connection string. That file is the development source of truth.
   Never commit `.env`.

3. **Precedence:** values in repository-root `.env` override stale shell
   exports. An empty `DATABASE_URL=` in `.env` means “not configured”, even if
   the shell still has an old local URL (e.g. `127.0.0.1/trading_dev`).

4. Persistent development data lives in **Supabase PostgreSQL**, not local
   Docker Postgres / `trading_dev`.

```bash
# connectivity (refuses local targets)
./scripts/check-database.sh

# migrate only after Supabase target confirmation
./scripts/migrate-supabase.sh
```

| Variable | Purpose |
|---|---|
| `APP_NAME` | Application name |
| `APP_ENV` | `development` / `staging` / `production` |
| `LOG_LEVEL` | Logging level |
| `API_HOST` / `API_PORT` | Bind host/port |
| `DATABASE_URL` | Supabase PostgreSQL URL (optional for early local dev) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (server only) |

The API **starts successfully** when `DATABASE_URL` is empty. Database
operations and Alembic migrations require a real connection string.

---

## Local development setup

Requires Python 3.12+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# from repository root
cp .env.example .env

# run API (from backend/)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: `curl http://127.0.0.1:8000/health`

---

## Docker startup

From the repository root (Compose file lives here; only the API service):

```bash
cp .env.example .env
docker compose up --build
```

- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`

PostgreSQL is **not** run in Docker Compose. Use Supabase for persistent data.

---

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

---

## Alembic (later)

Once `DATABASE_URL` points at Supabase:

```bash
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

No trading schema migrations exist yet.
