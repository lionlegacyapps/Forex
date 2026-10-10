# GitHub Strategy Intake & Adapter Framework V1

## EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.

Any repository must pass **License**, **Security**, **Architecture**,
**Dependency**, and **Backtest** review before integration.

```
GitHub Repo
  → Intake Review
  → License Review
  → Dependency Review
  → Security Review
  → Architecture Classification
  → Algorithm Extraction / Safe Wrapper
  → Internal Strategy Adapter
  → Strategy Registry
  → Backtest
  → QA
  → Paper eligibility
```

**Never:**

```
GitHub Repo → execute directly → Broker
```

V1 prepares the framework. It does **not** clone repositories and does
**not** execute external GitHub strategy code.

---

## Intake model

`ExternalRepositoryIntake` captures optional metadata: URL, name, owner,
license, language, dependency/strategy files, backtesting/broker/market-data
integrations, AI/ML components, network/filesystem/shell/dynamic-exec flags,
security warnings, and integration recommendation.

## Classification

`RepoClassification` (multi-select):

- `STRATEGY_ALGORITHM`
- `BACKTESTING_LIBRARY`
- `INDICATOR_LIBRARY`
- `PORTFOLIO_RISK_LIBRARY`
- `MARKET_DATA_TOOL`
- `EXECUTION_BROKER_TOOL`
- `ML_AI_RESEARCH`
- `FULL_TRADING_BOT`
- `REFERENCE_ONLY`
- `UNKNOWN`

## Integration decisions

`IntegrationRecommendation`:

| Recommendation | Meaning |
|---|---|
| `ADAPT_ALGORITHM` | Extract useful logic into our typed Strategy adapter |
| `WRAP_LIBRARY` | Thin wrap of a small, approved library |
| `USE_AS_DEPENDENCY` | Install only when clearly necessary & license-ok |
| `REFERENCE_ONLY` | Learn from it; do not vendor/execute |
| `REJECT` | Do not integrate |

Reasons are explicit (unsafe broker coupling, license, abandoned deps,
shell execution, hard-coded credentials, architecture mismatch, etc.).

## License safety

Recognizes MIT, Apache-2.0, BSD, GPL, AGPL, LGPL, MPL, proprietary/custom,
no license.

Flags (not legal advice):

- `NO_LICENSE`
- `UNKNOWN_LICENSE`
- `COPYLEFT_REVIEW_REQUIRED`
- `AGPL_REVIEW_REQUIRED`
- `PERMISSIVE_OK`
- `CUSTOM_REVIEW_REQUIRED`

Do **not** copy code from unclear/incompatible licensing.

## Security review

Static pattern rules over provided source snippets (not executed):

subprocess / `os.system` / `shell=True`, `eval`, `exec`, pickle, dynamic
import, credential patterns, env access, HTTP clients, filesystem writes,
Docker socket, SSH, broker order submission, webhooks, unsafe deserialize.

**Static scanning does not prove safety.**

## Broker isolation

Repos that place broker orders require isolation. We may extract strategy
logic only. Execution always remains:

```
StrategyDecision → Trade Proposal → Risk → Validator → Broker Router → Broker
```

## Adapter contract

`ExternalStrategyAdapter` (extends `Strategy`):

1. `map_context(StrategyContext) → algorithm_input`
2. `run_algorithm(algorithm_input) → algorithm_output`
3. `to_decision(algorithm_output, context) → StrategyDecision`

Never exposes: broker execution, credentials, raw DB sessions.

Registration goes through `GatedStrategyRegistry` /
`IntakeRegistrationGate`. Untrusted repo URLs/intake blobs cannot register
as `Strategy` directly. Rejected manifests cannot become active strategies.

## Sandbox boundary (future)

Documented in `SandboxBoundarySpec` / `SANDBOX_REQUIREMENTS`:

- no broker credentials
- no Supabase service-role key
- no host filesystem
- no Docker socket
- limited/no network
- resource limits + timeouts

**V1 does not auto-execute external code.**

## Repository manifest

`RepositoryManifest`: repository, revision (commit SHA), license,
classification, integration_mode, approved/rejected files, dependencies,
security findings, adapter_name, status.

Statuses: `candidate`, `reviewing`, `approved_for_adaptation`, `rejected`,
`integrated`, `retired`.

## Version pinning

Approved adaptations **must** pin an exact commit SHA (or short SHA).
Floating refs (`latest`, `main`, `master`, `HEAD`) are rejected.

## Dependency policy

Prefer extracting a small algorithm into our typed implementation over
installing a large framework when practical and license-compatible.
Avoid duplicate backtesting/execution frameworks unless clear benefit.

## Adapter test harness

`run_adapter_harness(strategy)` checks:

- valid StrategyContext input
- deterministic output
- parameter validation
- no broker imports / credential access
- decision → Trade Proposal compatibility
- backtest compatibility + reproducibility

## Review report

`RepoReviewReport` / `build_review_report` fields:

REPOSITORY, PURPOSE, LICENSE, MAINTENANCE STATUS, ARCHITECTURE,
USEFUL COMPONENTS, BROKER COUPLING, SECURITY FINDINGS, DEPENDENCY COST,
INTEGRATION RECOMMENDATION, INTEGRATION METHOD, RISK LEVEL.

## Next milestone (not this one)

Provide **one specific** GitHub repository URL for intake review using this
framework. Still no blind vendoring; still no direct execution; still no
live trading / Tradovate.

## Related

- [strategy-engine-backtesting-v1.md](./strategy-engine-backtesting-v1.md)
- [trading-safety-pipeline-v1.md](./trading-safety-pipeline-v1.md)
- [architecture.md](./architecture.md)
