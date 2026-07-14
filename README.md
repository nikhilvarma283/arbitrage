# Arbitrage: Algorand Atomic Arbitrage Bot

A capital-efficient, safety-first crypto market microstructure bot starting with Algorand DEX arbitrage. This repository implements the Phase 1 roadmap from the Crypto Microstructure Revenue Program.

**Current Status:** Gate 0 (Shadow Mode) - Development in Progress  
**Phase:** 1 (Algorand Foundation)  
**Target Launch:** Month 2 (Live Trading)

## 📖 Documentation

- **[PHASE_1_SPRINT_ROADMAP.md](../PHASE_1_SPRINT_ROADMAP.md)** — Complete development roadmap with 6 sprints
- **[GITHUB_ISSUES_TEMPLATE.md](../GITHUB_ISSUES_TEMPLATE.md)** — Ready-to-import GitHub issues
- **[PHASE_1_QUICK_REFERENCE.md](../PHASE_1_QUICK_REFERENCE.md)** — Operations & emergency procedures

## 🎯 Quick Start

### Prerequisites
- Python 3.11+
- Git & GitHub account
- Algorand Foundation research (optional, for context)

### Local Development Setup

```bash
# Clone this repository
git clone https://github.com/nikhilvarma283/arbitrage.git
cd arbitrage

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Code quality checks
black . && ruff check . && mypy src/
```

## 📁 Repository Structure

```
arbitrage/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── pyproject.toml                     # Project metadata & tools config
│
├── .github/
│   └── workflows/
│       ├── test.yml                   # Run tests on PR/push
│       ├── lint.yml                   # Code quality checks
│       └── deploy.yml                 # Manual deployment to VPS (Phase 1 only)
│
├── src/
│   ├── __init__.py
│   ├── pool_watcher.py               # Block listener, pool state tracking (Sprint 2)
│   ├── opportunity_engine.py         # Spread detection, opportunity sizing (Sprint 2)
│   ├── executor.py                   # Atomic transaction builder (Sprint 3, Phase 1 only)
│   ├── safety.py                     # 4-layer circuit breakers (Sprint 3)
│   ├── ledger.py                     # SQLite trade logging (Sprint 2)
│   ├── alerts.py                     # Telegram notifications (Sprint 4)
│   ├── watchdog_client.py            # Heartbeat to independent watchdog (Sprint 3)
│   └── utils.py                      # Shared utilities (constants, math, etc.)
│
├── tests/
│   ├── __init__.py
│   ├── test_pool_watcher.py
│   ├── test_opportunity_engine.py
│   ├── test_executor.py
│   ├── test_safety.py
│   ├── test_ledger.py
│   └── fixtures/                     # Test data, mock blocks
│       └── pool_states.json
│
├── config/
│   ├── bot.yaml.example              # Configuration template (secrets in .env)
│   └── .env.example                  # Environment variables template
│
├── scripts/
│   ├── cold_sweep.py                 # Daily profit sweep to cold wallet
│   ├── health_check.py               # Node/bot health monitoring
│   ├── export_dashboard_data.py      # Export metrics for public dashboard
│   └── deploy.sh                     # Deployment script to VPS
│
├── docs/
│   ├── ARCHITECTURE.md               # System design & data flow
│   ├── API.md                        # Ledger/dashboard API docs
│   ├── SAFETY.md                     # Safety architecture & trip-switches
│   └── OPERATIONS.md                 # Runbook for operators
│
├── Dockerfile                         # Container image for bot
├── docker-compose.yml                 # Local dev: algod + bot + monitoring
│
├── .gitignore                         # Ignore secrets, ledger, logs
└── CONTRIBUTING.md                    # Contributing guidelines
```

## 🚀 Phases & Gates

### Phase 1: Algorand (This Repository)
- **Gate 0 (Shadow):** Weeks 1-4, $700 capital
  - Shadow harness: detect opportunities, zero capital at risk
  - Exit: 14-30 days logs, flow ≥50% of model
  
- **Gate 1 (Live):** Weeks 5-8, $6,500 capital
  - Execute trades, full safety architecture
  - Exit: Win rate ≥40%, net ≥$3K/month
  
- **Gate 2 (Extended):** Weeks 9-16, $8,000 capital
  - Add O2 (multi-hop) and O3 (liquidations) modules
  - Exit: Combined net ≥$8K/month

### Phase 2: Solana (Separate Repository Later)
- Atomic arbitrage on Solana
- Incremental net ≥$4K/month

### Phase 3: Capital & Intent Solving (Later)
- Funding-rate basis trading
- Intent solving / order-flow auctions

## 📊 Key Metrics

### Daily Tracking
- **Win Rate:** Target ≥40% (attempted races won)
- **Daily Net:** Target ≥$100 ($3K/month target)
- **Capture vs. Model:** Target ≥50% (actual / simulated)

### Gate Criteria
- **Gate 0 Pass:** Flow ≥50% of model, 14+ days logs
- **Gate 1 Pass:** Win rate ≥40%, net ≥$3K/month over 60 days
- **Gate 2 Pass:** Combined net ≥$8K/month

See [PHASE_1_QUICK_REFERENCE.md](../PHASE_1_QUICK_REFERENCE.md) for full KPI dashboard.

## 🛡️ Safety Architecture

**4-Layer Circuit Breaker System (mandatory from first commit):**

1. **Layer 0: Consensus-Enforced Atomicity**
   - On-chain profit assertion + revert guarantee
   - Worst case per trade: network fee (~$0.001)

2. **Layer 1: In-Bot Breakers** (auto-halt on)
   - 5 consecutive failed submissions
   - Daily fee/tip burn >$300 (15% of gross)
   - Any negative profit detected (impossible by Layer 0)
   - Wallet balance deviation from ledger

3. **Layer 2: Anomaly Ceiling**
   - Spreads >3× historical max trigger stand-down
   - Detects dislocation/exploit in progress

4. **Layer 3: Independent Watchdog**
   - Separate VPS monitoring bot heartbeat
   - Emergency kill-switch on unresponsiveness
   - Pages operator on critical failure

5. **Layer 4: Structural Containment**
   - Hot wallet capped at $2K (working float only)
   - Daily cold sweep of profits
   - Per-trade position limits
   - Separate cold wallet (hardware wallet recommended)

## 📋 Development Workflow

### Before Opening a PR
1. Fork this repository (if contributing)
2. Create a feature branch: `git checkout -b feature/pool-watcher`
3. Write tests first (TDD)
4. Run linting & type-checking:
   ```bash
   black . && ruff check . && mypy src/
   ```
5. Run full test suite:
   ```bash
   pytest tests/ -v
   ```
6. Open a Pull Request with:
   - Clear description of what/why
   - Link to GitHub issue (if applicable)
   - Test results screenshot

### Branch Protection Rules
- `main` branch: require PR review + all CI checks passing
- `develop` branch: require CI checks passing
- Force push disabled on both

### GitHub Issues & Projects
- Use [GitHub Issues](https://github.com/nikhilvarma283/arbitrage/issues) to track work
- Organize by sprint (Sprint 1, Sprint 2, etc.)
- Use labels: `p0` (critical), `p1` (high), `p2` (medium), `feature`, `bug`, `ops`
- See [GITHUB_ISSUES_TEMPLATE.md](../GITHUB_ISSUES_TEMPLATE.md) for ready-to-import issues

## 🔐 Security

**Before Any Live Trading:**
- [ ] CPA engagement for tax guidance
- [ ] Algorand Foundation consulting agreement review
- [ ] Section 2 exclusions checklist approved (no sandwich attacks, no retail extraction)
- [ ] All safety layers tested end-to-end
- [ ] Watchdog kill-switch verified
- [ ] Cold wallet secured (hardware wallet recommended)

**Secrets Management:**
- Use `.env` file (never commit)
- Use GitHub Secrets for CI/CD deployments
- All keys encrypted at rest on VPS (age or sops)

**Incident Response:**
- See [PHASE_1_QUICK_REFERENCE.md](../PHASE_1_QUICK_REFERENCE.md) for emergency procedures
- Negative profit detected → full stop + post-mortem
- Server compromise → kill bot, transfer remaining float to cold wallet

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Current team:**
- **Founder/Operator:** You (nikhilvarma283)
- **Backend Engineer:** [To be assigned]
- **Blockchain Engineer:** [To be assigned]
- **DevOps:** [To be assigned]
- **QA:** [To be assigned]

## 📚 Resources

- **Algorand Documentation:** https://developer.algorand.org
- **py-algorand-sdk:** https://py-algorand-sdk.readthedocs.io
- **Tinyman v2:** https://docs.tinyman.org
- **Pact:** https://docs.pactfi.com

## 📄 License

[Choose your license: MIT, Apache 2.0, or Proprietary]

## ⚖️ Disclaimer

This software is analytical planning material and does **not constitute financial, legal, or tax advice**. The modeled figures are planning estimates derived from simulation, not guarantees of future results.

Before live trading:
- Engage a CPA for tax guidance
- Review applicable laws and regulations
- Obtain necessary agreements (Algorand Foundation, exchanges)
- Implement all safety systems
- Thoroughly test with small amounts first

**Sunk cost if thesis fails:** <$1,000 (intentionally minimal by design)

---

**Last Updated:** July 13, 2026  
**Status:** Gate 0 (Shadow Mode) - Sprint 1 Starting  
**Next Review:** End of Sprint 2 (Week 4)
