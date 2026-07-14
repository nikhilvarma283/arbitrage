# Sprint 2: Shadow Harness Development

**Duration:** Weeks 3-4 (plus 14-30 day continuous test run)  
**Gate:** Gate 0 (Shadow Mode)  
**Status:** 🚀 Starting now (skipped Sprint 1 infrastructure)

## 📋 Sprint 2 Tasks

### S2.1: Pool Watcher Module ✏️ **READY TO CODE**
**File:** `src/pool_watcher.py`  
**Time:** 4-5 days  
**Status:** Skeleton with detailed TODO comments

**Responsibilities:**
- Subscribe to Algorand mainnet block stream
- Extract pool state (reserves) for Tinyman v2 and Pact pools
- Maintain in-memory cache of current pool reserves
- Emit events to opportunity_engine on pool updates
- Track metrics (blocks processed, missed blocks, errors)

**Key Classes:**
- `PoolState` — Data class for pool state
- `PoolWatcher` — Main listener class with `start()`, `get_pool_state()`, etc.

**Test File:** `tests/test_pool_watcher.py` (skeleton with TODO tests)

**Exit Criteria:**
- Pool state updates match indexer API within 1 block
- Zero missed blocks over 24h test run
- Sub-100ms update latency per block
- All unit tests passing

---

### S2.2: Opportunity Engine Module ✏️ **READY TO CODE**
**File:** `src/opportunity_engine.py`  
**Time:** 5-6 days  
**Status:** Skeleton with detailed TODO comments

**Responsibilities:**
- Receive pool state updates from pool_watcher
- Compute inter-pool spreads (dislocation)
- Apply 55 bps gate (discard spreads <0.55%)
- Size trades using constant-product formula mathematics
- Rank opportunities by expected profit
- Forward executable opportunities to executor (Phase 1 only)

**Key Classes:**
- `Opportunity` — Data class for detected opportunity
- `OpportunityEngine` — Main detection logic with `detect_opportunities()`, `compute_spread()`, `size_trade()`, etc.
- `OpportunityEngineConfig` — Configuration management

**Critical Math:**
```
For pools A (cheap) → B (rich):
y = (reserve_b_A * X * (1 - fee_a)) / (reserve_a_A + X * (1 - fee_a))
output = (reserve_a_B * y * (1 - fee_b)) / (reserve_b_B + y * (1 - fee_b))
profit = X - output

Optimal X: Use golden-section search or closed-form solution
```

**Test File:** `tests/test_opportunity_engine.py` (skeleton with TODO tests)

**Exit Criteria:**
- Math checks against hand-computed routes on 10+ fixtures (exact ±0.01%)
- Gate logic correctly rejects sub-threshold spreads
- Sizing never violates position limits
- Simulation reproduction matches live data within ±5%

---

### S2.3: SQLite Ledger Module ✏️ **READY TO CODE**
**File:** `src/ledger.py`  
**Time:** 3 days  
**Status:** Skeleton with detailed TODO comments

**Responsibilities:**
- Create and maintain SQLite database schema
- Log all detected opportunities (shadow mode)
- Log all submitted trades (phase 1 live)
- Compute daily KPIs (win rate, net profit, decay ratio)
- Export data for public dashboard
- Validate database integrity

**Database Schema:**
```sql
opportunities:
  - timestamp, block_number
  - pool_a_id, pool_b_id, spread_bps, size, profit
  - indexes on timestamp

trades:
  - tx_group_id (PK), timestamp
  - pool_a_id, pool_b_id, spread_bps, size
  - status (submitted/won/lost/failed)
  - actual_profit_usd, gas_spent_usd
  - indexes on timestamp, status

daily_summary:
  - date (PK)
  - opportunities_detected, avg_spread_bps
  - trades_submitted, trades_won, win_rate
  - total_profit_usd, total_gas_usd, net_profit_usd
  - decay_ratio (this week / last week)
```

**Key Classes:**
- `Ledger` — Main class with `log_opportunity()`, `log_trade()`, `update_trade_result()`, `get_daily_summary()`, `validate()`, etc.
- `LedgerConfig` — Configuration management

**Test File:** `tests/test_ledger.py` (skeleton with TODO tests)

**Exit Criteria:**
- Zero missed log writes under sustained load
- Database survives 1M+ record insertion
- Graceful recovery from corruption
- Export matches raw ledger on spot-check

---

### S2.4: Public Dashboard & Data Export ✏️ **READY TO CODE**
**File:** Implement as FastAPI/Flask service (create `src/dashboard.py` and `scripts/run_dashboard.py`)  
**Time:** 4-5 days  
**Status:** Skeleton guide (API endpoints specified)

**Responsibilities:**
- Expose metrics API (GET endpoints for daily/hourly metrics)
- Serve static HTML dashboard (no auth required, public)
- Export opportunity data for analysis
- Metrics include: dislocation frequency, spreads, competition signals

**API Endpoints:**
```
GET /metrics/daily?date=2026-07-13
  Returns: daily KPIs (opportunities, win_rate, net_profit, decay_ratio)

GET /metrics/hourly?start=2026-07-01&end=2026-07-13
  Returns: hourly metrics (opportunities/hour, avg_spread_bps)

GET /opportunities?start_date=2026-07-01&end_date=2026-07-13&limit=1000
  Returns: opportunity list (pool_a, pool_b, spread_bps, profit_usd)

GET /health
  Returns: health status, data freshness
```

**Frontend Design:**
- Header: "Algorand DEX Microstructure Dashboard"
- Live metrics cards: opportunities/hour, avg spread, today's profit, decay ratio
- Charts: 24h spread trend, opportunities/hour, profit/hour, decay ratio
- Opportunity feed: scrollable list of recent opportunities

**Test File:** Create `tests/test_dashboard.py` (implement as you build)

**Exit Criteria:**
- All API endpoints working
- Dashboard loads and displays correctly
- Responsive design (mobile/tablet/desktop)
- Real-time updates every 10s

---

### S2.5: Integration & 14-30 Day Test Run ✏️ **READY TO CODE**
**File:** `src/main.py` (integrate all modules)  
**Time:** 2-3 days setup + 14-30 days continuous run  
**Status:** Guide (orchestrate S2.1-S2.4)

**Integration Steps:**
1. Create `src/main.py` orchestrating all modules
2. Implement main loop:
   ```python
   while running:
       block = pool_watcher.fetch_latest_block()
       opportunities = opportunity_engine.detect(pools)
       for opp in opportunities:
           ledger.log_opportunity(opp)
   ```
3. Deploy to VPS (Docker Compose)
4. Run continuously for 14-30 days
5. Validate Gate 0 metrics

**Gate 0 Exit Criteria:**
- ✅ Opportunity flow ≥50% of model (≥3K per month baseline)
- ✅ Zero missed blocks or ledger corruption
- ✅ Dashboard metrics align with model predictions
- ✅ All logs and documentation complete

**Test File:** `tests/test_integration.py` (implement as you build)

---

## 📁 Files Structure (Sprint 2 Complete)

```
arbitrage/
├── src/
│   ├── __init__.py
│   ├── pool_watcher.py          ← S2.1 (implement)
│   ├── opportunity_engine.py    ← S2.2 (implement)
│   ├── ledger.py                ← S2.3 (implement)
│   ├── alerts.py                ← S2.4 (implement, basic Telegram)
│   ├── main.py                  ← S2.5 (integrate all)
│   └── dashboard.py             ← S2.4 (API server)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              ✅ (done)
│   ├── test_pool_watcher.py     ← S2.1 (implement)
│   ├── test_opportunity_engine.py ← S2.2 (implement)
│   ├── test_ledger.py           ← S2.3 (implement)
│   ├── test_alerts.py           ← S2.4 (implement)
│   ├── test_integration.py      ← S2.5 (implement)
│   └── fixtures/
│       └── pool_states.json     (create fixture data)
│
├── scripts/
│   ├── run_dashboard.py         ← S2.4 (serve metrics API)
│   └── health_check.py          (monitor bot/node)
│
├── config/
│   ├── bot.yaml.example         ✅ (done)
│   └── .env.example             ✅ (done)
│
├── docs/
│   ├── ARCHITECTURE.md          ✅ (done)
│   └── SPRINT_2_README.md       ← (this file)
│
├── SPRINT_2_README.md           ← YOU ARE HERE
└── README.md                    ✅ (done)
```

## 🔧 Implementation Guide

### Step 1: Pool Watcher (S2.1) - Days 1-5
**Start:** `src/pool_watcher.py`

1. Set up py-algorand-sdk client
2. Implement block subscription (use `algod_client.block_subscribe()` or indexer)
3. Parse block application state for Tinyman v2 and Pact pools
4. Update in-memory cache of reserves
5. Implement error handling (RPC timeouts, missed blocks)
6. Write unit tests
7. Test on testnet for 24h

**Deliverable:** Continuous block listener with sub-100ms latency

---

### Step 2: Opportunity Engine (S2.2) - Days 6-11
**Start:** `src/opportunity_engine.py`

1. Implement `compute_spread()` — Calculate dislocation between pools
2. Implement `size_trade()` — Constant-product formula with optimal sizing
3. Implement gates (spread gate, profit gate, size gates)
4. Implement `detect_opportunities()` — Main detection loop
5. Implement ranking by profit
6. Write unit tests against 10 hand-computed fixtures
7. Test on testnet

**Deliverable:** Opportunity detection engine with ±5% accuracy vs. model

---

### Step 3: SQLite Ledger (S2.3) - Days 12-14
**Start:** `src/ledger.py`

1. Design and create SQLite schema
2. Implement `log_opportunity()` and `log_trade()`
3. Implement `update_trade_result()`
4. Implement `get_daily_summary()` — KPI calculation
5. Implement `export_for_dashboard()`
6. Implement `validate()` — Integrity check
7. Write unit tests
8. Stress test with 1M+ records

**Deliverable:** Persistent, validated audit log with fast queries

---

### Step 4: Dashboard & Alerts (S2.4) - Days 15-19
**Start:** `src/dashboard.py` + `src/alerts.py`

1. Create FastAPI/Flask server with `/metrics/daily`, `/metrics/hourly`, `/opportunities`, `/health` endpoints
2. Build static HTML dashboard
3. Implement Telegram alert manager (`send_fill()`, `send_breaker()`, `send_daily_summary()`)
4. Write unit tests
5. Deploy on port 8080 on VPS

**Deliverable:** Public dashboard + operator alerts

---

### Step 5: Integration & 14-30 Day Test (S2.5) - Days 20-22 + 14-30 days
**Start:** `src/main.py`

1. Create main orchestration loop (pool_watcher → opportunity_engine → ledger → alerts)
2. Implement Docker Compose (algod + bot + monitoring)
3. Deploy to VPS
4. Run 14-30 days continuously in shadow mode
5. Monitor Gate 0 metrics:
   - Flow ≥50% of model
   - Zero missed blocks
   - Ledger integrity
   - Dashboard accuracy

**Deliverable:** Validated shadow harness, ready for Phase 1 live trading

---

## 🧪 Testing Strategy

### Unit Tests (TDD)
- Write tests before implementation
- Mock Algorand SDK, pool data, etc.
- Target ≥80% code coverage
- Each module has dedicated test file

### Integration Tests
- Test pool_watcher + opportunity_engine end-to-end
- Replay historical block data
- Compare to expected opportunity flow

### Shadow Mode Test (14-30 days)
- Run on mainnet in detection-only mode
- Validate flow ≥50% of model
- Zero missed blocks, ledger integrity
- Real operator validation

---

## 📊 Development Progress Tracking

Use GitHub Issues & Project Board:

1. Create issues for S2.1 through S2.5 (from GITHUB_ISSUES_TEMPLATE.md)
2. Add labels: `sprint-2`, `p0`, feature/backend
3. Move to "In Progress" as you start each task
4. Link PRs to issues: "Closes #123" in PR description
5. Move to "Done" when PR merged

**GitHub Actions Automated:**
- Linting (black, ruff)
- Type checking (mypy)
- Unit tests (pytest)
- Coverage report (pytest-cov)

---

## 🚀 How to Run Locally

### Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt

# Verify algod node is running (requires Sprint 1 setup)
# For now, can use testnet or mock data
```

### Run Tests
```bash
# All tests
pytest tests/ -v

# Specific module
pytest tests/test_pool_watcher.py -v

# With coverage
pytest tests/ -v --cov=src
```

### Run Code Quality Checks
```bash
# Format with black
black src/ tests/

# Lint with ruff
ruff check src/ tests/

# Type check with mypy
mypy src/ --ignore-missing-imports
```

### Run Shadow Harness (local)
```bash
# Set up config
cp config/bot.yaml.example config/bot.yaml
cp config/.env.example config/.env
# Edit with your settings

# Run main loop (after all modules implemented)
python -m src.main
```

---

## ⚠️ Important Notes

### Decimal Precision
Use `Decimal` type for all financial calculations (not float) to avoid precision errors.

```python
from decimal import Decimal
profit = Decimal("1000.50")  # ✅ Correct
profit = 1000.50  # ❌ Risky (float precision)
```

### No Database Files in Repo
SQLite ledger.db is in `.gitignore`. Never commit it.

### Configuration
- Pool IDs, gates: in `config/bot.yaml`
- Secrets (keys, tokens): in `.env` (git-ignored)
- Never hardcode secrets in Python files

### Error Handling
- RPC failures: retry with exponential backoff
- Missed blocks: backfill from indexer
- Ledger corruption: restore from backup

---

## 📝 Documentation to Update

As you implement, update:
- `docs/ARCHITECTURE.md` — Add module details
- `README.md` — Update status
- Docstrings in each module
- `tests/` — Add integration test docs

---

## 🎯 Gate 0 Success Criteria

At end of Sprint 2 (14-30 day test):

- ✅ Shadow harness running continuously
- ✅ Opportunity flow ≥50% of model (≥3K opportunities per month)
- ✅ Zero missed blocks or ledger corruption
- ✅ Dashboard metrics accurate and live
- ✅ All logs and documentation complete
- ✅ Team trained on bot operation

**Result:** Approved to proceed to Phase 1 (live trading with safety layers)

---

## 📞 Support

- Questions? Post in GitHub Issues
- Blockers? Create GitHub Issue with `blocked` label
- Architecture? Check `docs/ARCHITECTURE.md`
- Testing? See `CONTRIBUTING.md`

---

**Sprint 2 Start Date:** TODAY  
**Estimated Completion:** 2-3 weeks (dev) + 2-4 weeks (shadow testing) = 4-7 weeks total  
**Gate 0 Decision:** End of test run (week 4-7)

---

**Let's build! 🚀**
