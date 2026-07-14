# Architecture Guide

## System Overview

The arbitrage bot is organized into independent modules that can be tested and deployed separately:

```
┌─────────────────────────────────────────────────────────┐
│ ALGORAND MAINNET                                         │
│ ├─ Tinyman v2 Pool (ALGO/USDC)                          │
│ └─ Pact DEX Pool (ALGO/USDC)                            │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ Block Stream
                          │
┌─────────────────────────────────────────────────────────┐
│ Arbitrage Bot (Python, Phase 1)                         │
│                                                          │
│  1. pool_watcher                                         │
│     ├─ Subscribe to blocks                              │
│     ├─ Extract pool state (reserves)                    │
│     └─ Emit PoolUpdated events                          │
│                     │                                    │
│                     ▼                                    │
│  2. opportunity_engine                                  │
│     ├─ Compute inter-pool spreads                       │
│     ├─ Apply 55 bps gate                                │
│     ├─ Size trades (constant product math)              │
│     └─ Rank opportunities by profit                     │
│                     │                                    │
│                     ▼                                    │
│  3. ledger (SQLite)                                      │
│     ├─ Log all opportunities (shadow mode)              │
│     ├─ Log all trades (live mode)                       │
│     └─ Export metrics to dashboard                      │
│                                                          │
│  4. alerts (Telegram)                                    │
│     ├─ Fills (successful trades)                        │
│     ├─ Breaker events                                   │
│     └─ Daily summary                                    │
│                                                          │
│  (Phase 1 Live Only):                                    │
│  5. executor (atomic transactions)                      │
│     ├─ Build transaction group                          │
│     ├─ Apply profit assertion                           │
│     └─ Sign and submit                                  │
│                     │                                    │
│                     ▼                                    │
│  6. safety (circuit breakers)                           │
│     ├─ Layer 1: in-bot checks                           │
│     ├─ Layer 2: anomaly ceiling                         │
│     ├─ Layer 3: watchdog                                │
│     └─ Layer 4: containment                             │
│                                                          │
│  7. watchdog_client (heartbeat)                         │
│     ├─ Send periodic heartbeat                          │
│     └─ Receive kill-switch commands                     │
└─────────────────────────────────────────────────────────┘
          ▲                                    │
          │ Heartbeat (30s)                    │ Telegram
          │                                    ▼
    ┌─────────────┐              ┌──────────────────────┐
    │ Watchdog    │              │ Telegram Bot         │
    │ (separate   │              │ (alerts, daily sum)  │
    │  VPS)       │              │                      │
    └─────────────┘              └──────────────────────┘
```

## Data Flow

### Shadow Mode (Gate 0)
```
Algorand Block Stream
        │
        ▼
pool_watcher → pool_state
        │
        ▼
opportunity_engine → opportunities
        │
        ▼
ledger.log_opportunity()
        │
        ▼
SQLite (opportunities table)
        │
        ▼
Dashboard export (public metrics)
```

### Live Mode (Gate 1+)
```
Same as shadow, but:

opportunity_engine
        │
        ▼ (only if profit > threshold)
executor → atomic transaction
        │
        ▼ (on-chain)
safety.check_result()
        │
        ├─ Profit asserted? YES → Won
        ├─ Reverted? YES → Lost race
        └─ Error? → Failed submission
        │
        ▼
ledger.log_trade(result)
        │
        ▼
SQLite (trades table)
        │
        ├─ Alerts (Telegram)
        └─ Dashboard export
```

## Module Responsibilities

### pool_watcher.py (Sprint 2)
**Responsibility:** Track real-time pool state from Algorand blocks

**Inputs:**
- Algorand block stream
- Pool configuration (pool IDs, asset IDs)

**Outputs:**
- PoolUpdated events
- Pool state cache (in-memory)

**Key Functions:**
- `subscribe_to_blocks()` → async listener
- `parse_block(block)` → extract pool state
- `get_current_reserves()` → return cached state

**Testing:**
- Mock blocks, verify state parsing
- Simulate missed blocks, verify recovery
- 24h continuous run, verify zero missed blocks

### opportunity_engine.py (Sprint 2)
**Responsibility:** Detect and size profitable arbitrage opportunities

**Inputs:**
- Pool state updates from pool_watcher
- Configuration (spread gate, profit thresholds)

**Outputs:**
- Opportunity objects (spread, size, expected profit)
- Ranked by profit

**Key Functions:**
- `detect_opportunities(pools)` → list of opportunities
- `compute_spread(pool_a, pool_b)` → spread in bps
- `size_trade(spread, pools)` → optimal trade size
- `filter_by_gates(opportunities)` → apply thresholds

**Testing:**
- Unit tests: math against hand-computed routes (10+ fixtures)
- Unit tests: spread calculation
- Unit tests: sizing edge cases (small spread, large spread, precision)
- Integration: pool updates → opportunities

### ledger.py (Sprint 2)
**Responsibility:** Persist all opportunities and trades to SQLite

**Inputs:**
- Opportunities (shadow mode)
- Trades & results (live mode)

**Outputs:**
- SQLite database
- Daily summaries (KPIs)
- Dashboard exports

**Key Tables:**
- `opportunities` — all detected, shadow mode
- `trades` — all submissions, live mode
- `daily_summary` — KPIs

**Testing:**
- Unit: schema, inserts, updates
- Stress: 1M+ writes, verify zero corruption
- Corruption: intentional DB damage, verify recovery

### executor.py (Sprint 3, Phase 1 Live Only)
**Responsibility:** Build, sign, and submit atomic transaction groups

**Inputs:**
- Opportunity from opportunity_engine
- Wallet configuration (address, keys)

**Outputs:**
- Transaction group ID
- Result (won, lost, failed)

**Key Functions:**
- `build_atomic_group(opp)` → AlgorandTransaction[]
- `sign_and_submit()` → tx_id
- `classify_result()` → won/lost/failed

**Testing:**
- Fuzz: testnet, all deliberately unprofitable groups → 100% revert
- Integration: devnet, 50+ successful trades
- Dry-run: mainnet shadow (no signing), verify group structure

### safety.py (Sprint 3)
**Responsibility:** Implement 4-layer circuit breaker system

**Inputs:**
- Trade results
- Bot state (balance, uptime)
- RPC/node health

**Outputs:**
- Halt/continue decision
- Alerts to operator

**Key Layers:**
1. Layer 0: On-chain assertion (must always revert on loss)
2. Layer 1: In-bot checks (5 failures, fee caps, balance deviation)
3. Layer 2: Anomaly ceiling (spreads > 3x max)
4. Layer 3: Watchdog (separate process, kill-switch)
5. Layer 4: Containment (hot wallet cap, cold sweep)

**Testing:**
- Fuzz: inject faults, verify correct breaker fires
- Integration: testnet, verify halt and resume

### alerts.py (Sprint 4)
**Responsibility:** Send notifications to operator

**Inputs:**
- Trade fills
- Breaker events
- Daily summary

**Outputs:**
- Telegram messages (formatted)

**Testing:**
- Unit: message formatting
- Integration: mock Telegram, verify sends

### watchdog_client.py (Sprint 3, Phase 1 Live Only)
**Responsibility:** Heartbeat to independent watchdog process

**Inputs:**
- Bot state (alive, synced, etc.)

**Outputs:**
- Heartbeat packets
- Kill-switch commands (from watchdog)

**Testing:**
- Integration: watchdog on separate VPS, verify heartbeat and kill

## Data Models

### PoolState
```python
@dataclass
class PoolState:
    pool_id: int
    pool_name: str
    asset_a_id: int
    asset_b_id: int
    reserve_a: Decimal
    reserve_b: Decimal
    fee_bps: int
    updated_at: int  # Block number
    updated_ts: datetime
```

### Opportunity
```python
@dataclass
class Opportunity:
    pool_a: PoolState
    pool_b: PoolState
    spread_bps: float
    size_tokens: Decimal
    expected_profit_tokens: Decimal
    expected_profit_usd: Decimal
    rank: int
    discovered_at: datetime
    expires_at: datetime
```

### Trade
```python
@dataclass
class Trade:
    tx_group_id: str
    timestamp: datetime
    pool_a: PoolState
    pool_b: PoolState
    spread_bps: float
    size_tokens: Decimal
    status: str  # "submitted", "won", "lost", "failed"
    actual_profit_usd: Optional[Decimal]
    gas_spent_usd: Optional[Decimal]
```

## Error Handling & Recovery

### Node Connection Loss
- Retry with exponential backoff (1s, 2s, 4s, 8s, 30s)
- After 30s retry, halt trading (Layer 1 breaker)
- Alert operator via Telegram

### Missed Block
- Detected: block numbers not sequential
- Action: backfill from indexer, continue
- Alert: log warning

### Executor Failure
- Timeout: retry once (might be network delay)
- RPC error: backoff and retry
- Persistent error: halt, investigate

### Database Corruption
- Detected: PRAGMA integrity_check fails
- Action: restore from backup, continue
- Alert: critical error, halt trading until investigated

## Testing Strategy

### Unit Tests (Per Module)
- Mock inputs, verify outputs
- Edge cases (zero, negative, precision)
- Error handling (invalid input, timeouts)

### Integration Tests
- Multiple modules together
- Mock Algorand blocks, verify end-to-end flow
- Ledger persistence

### Smoke Tests (Before Gate 0)
- 24h continuous run, shadow mode
- Verify: zero missed blocks, ledger integrity, alerts working

### Performance Tests
- Block processing latency: <100ms per block
- Database queries: <10ms for daily summary
- Opportunity detection: <1ms per pool pair

## Configuration & Secrets

### Sensitive Data
- Never hardcode secrets in code
- Use environment variables or encrypted files
- GitHub Secrets for CI/CD only

### Configuration
- YAML for non-secret config (pools, thresholds, etc.)
- Environment variables for secrets
- `.env` file locally (never commit)

## Deployment

### Local Development
- Docker Compose: algod node + bot
- SQLite ledger locally
- Tests against testnet

### Staging (VPS)
- Same as production, but testnet
- Shadow mode only (no live capital)
- Test for 72 hours before production

### Production (VPS)
- Docker Compose on hardened VPS
- PostgreSQL for ledger (optional upgrade from SQLite)
- Separate watchdog VPS
- Cold storage for profits
- Continuous monitoring & alerting

---

**Last Updated:** July 13, 2026  
**Sprint:** 2 (planning) to 4 (complete for Phase 1)
