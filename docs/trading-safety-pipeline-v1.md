# Trading Safety Pipeline V1

## Mandatory flow

```
Trade Proposal
      ↓
Risk Engine
      ↓
Order Validator
      ↓
Broker Router
      ↓
Simulation Broker
```

**REAL BROKER EXECUTION IS NOT IMPLEMENTED.**

No component may submit an order without passing every upstream gate.
Strategies, AI, signals, and manual entry must eventually create a
`TradeProposal` first. Broker adapters never decide whether a trade is safe.

## Components

| Component | Responsibility |
|---|---|
| `TradeProposalService` | Create proposals; orchestrate risk → validate → route |
| `RiskEngine` | Deterministic allow/deny (no AI) |
| `RiskPolicyResolver` | Merge multi-scope policies (strictest wins) |
| `OrderValidator` | Structural order consistency |
| `BrokerRouter` | Adapter selection; rejects unvalidated proposals |
| `SimulationBroker` | In-process PAPER adapter; **zero network calls** |
| `AuditService` | Append-only decision trail (no secrets) |

There is **no public HTTP execution endpoint** in this milestone.

## Risk policy resolution

Applicable **enabled** policies: GLOBAL → BROKER_ACCOUNT → STRATEGY →
STRATEGY_ACCOUNT, plus assignment numeric caps.

- Numeric maximums → **minimum** of all non-null values (strictest).
- `require_stop_loss` → **TRUE** if any applicable policy requires it;
  default **TRUE** when no policies exist.
- A more specific policy may tighten limits; it cannot silently raise an
  effective maximum above a stricter higher-scope value.

## Proposal state transitions

Allowed:

- `pending` → `risk_approved` | `risk_rejected`
- `risk_approved` → `validated` | `validation_rejected`
- `validated` → `routed` → `submitted`

Illegal examples (rejected):

- `pending` → `submitted`
- `risk_rejected` → `submitted`
- `submitted` → `pending`

## Risk reason codes (selected)

| Code | Meaning |
|---|---|
| `BROKER_ACCOUNT_DISABLED` | Account `is_enabled=false` |
| `LIVE_TRADING_NOT_ALLOWED` | Non-PAPER mode |
| `STRATEGY_NOT_ASSIGNED` / `STRATEGY_ASSIGNMENT_DISABLED` | Assignment gate |
| `STOP_LOSS_REQUIRED` | Effective policy requires `stop_loss_price` |
| `QUANTITY_INVALID` | Quantity ≤ 0 |
| `MAX_POSITION_SIZE_EXCEEDED` | Quantity over assignment cap |
| `MAX_ORDER_VALUE_EXCEEDED` | Calculable limit×qty over cap |
| `NOT_EVALUATED_MARKET_PRICE_REQUIRED` | Cap exists but no deterministic price |
| `NOT_EVALUATED_PNL_DATA_UNAVAILABLE` | Daily loss cap without reliable PnL |
| `DUPLICATE_PROPOSAL` | Active idempotency_key collision |
| `UNSUPPORTED_BROKER` | Account broker ≠ `simulation` |
| `RISK_ENGINE_ERROR` / `ORDER_VALIDATION_ERROR` / `BROKER_ROUTER_ERROR` | Fail-closed |

## Fail-closed behavior

Unexpected exceptions in Risk Engine, Order Validator, or Broker Router
**never** produce approval, validation success, routing, or submission.
The pipeline records a `PIPELINE_ERROR` audit event and rejects.

## Simulation limitations

- Provider slug: `simulation` only
- Generates `sim_<uuid>` broker order ids
- Accepts PAPER orders; does **not** auto-fill without deterministic pricing
- `get_quote` / bars / trades return unavailable / empty — no fabricated prices
- Makes **zero** external network calls
- Unknown brokers (e.g. `alpaca`) are rejected with `UNSUPPORTED_BROKER`
  (no silent simulation fallback)

## Idempotency note

Optional `idempotency_key` is stored in proposal `metadata` and checked for
active duplicates. Durable uniqueness would eventually need a dedicated
column + unique constraint on `(broker_account_id, idempotency_key)`.
No weak time-window heuristic is used.

## Audit events

`TRADE_PROPOSAL_CREATED`, `RISK_APPROVED`, `RISK_REJECTED`,
`ORDER_VALIDATED`, `ORDER_VALIDATION_REJECTED`, `ORDER_ROUTED`,
`SIMULATION_ORDER_SUBMITTED`, `PIPELINE_ERROR`
