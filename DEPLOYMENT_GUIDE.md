# Sprint 2 Deployment Guide - Local Testing to Production

**Status:** All Sprint 2 modules complete (S2.1-S2.5)  
**Ready for:** Testing, Shadow Mode, Gate 0 Validation  
**Commits:** 4 (init, scaffold, core, integration)  

---

## 📋 Prerequisites

### Hardware
- **Minimum:** 4 vCPU, 8GB RAM, 100GB storage
- **Recommended:** 8 vCPU, 16GB RAM, 240GB NVMe (Hetzner CPX41)

### Software
- Docker & Docker Compose
- Python 3.11 (for local development)
- Git

### Access
- Algorand Mainnet access (via Nodely, AlgoNode, or self-hosted node)
- Telegram bot token (for alerts)

---

## 🏃 Quick Start (5 minutes)

### Option 1: Docker (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/nikhilvarma283/arbitrage.git
cd arbitrage && git checkout develop

# 2. Create configuration
cp config/bot.mainnet.yaml config/bot.yaml
# Edit config/bot.yaml with your settings

# 3. Create .env for secrets
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
EOF

# 4. Start bot with Docker Compose
docker-compose up -d

# 5. Check logs
docker-compose logs -f bot

# 6. Health check
docker-compose exec bot python scripts/health_check.py
```

### Option 2: Local Python (Development)

```bash
# 1. Clone and setup
git clone https://github.com/nikhilvarma283/arbitrage.git
cd arbitrage && git checkout develop
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Create config
cp config/bot.mainnet.yaml config/bot.yaml
# Edit as needed

# 3. Start algod node separately (required)
# Ensure you have algod running on localhost:4001

# 4. Run bot
python -m src.main --config config/bot.yaml --mode shadow

# 5. Monitor
tail -f /data/logs/bot.log
```

---

## 🔧 Configuration

### 1. Basic Setup

**config/bot.yaml:**
```yaml
app:
  mode: "shadow"  # Start in shadow mode (detection only)
  
blockchain:
  algod_host: "localhost"  # Or your node IP
  algod_port: 4001
  
pools:
  - name: "TINYMAN_ALGO_USDC"
    pool_id: 430731383
    # ... (see config/bot.mainnet.yaml for full example)
```

### 2. Alerts Setup

Create `.env` file:
```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
```

Get Telegram tokens:
1. Create bot via [@BotFather](https://t.me/botfather)
2. Get your chat ID from [@userinfobot](https://t.me/userinfobot)
3. Add tokens to `.env`

### 3. Database Setup

Database creates automatically on first run:
```bash
# Check database integrity
python scripts/health_check.py
```

---

## 🧪 Testing Strategy

### Phase 1: Unit Tests (24 hours)

```bash
# Run all tests
pytest tests/ -v --cov=src

# Test specific module
pytest tests/test_pool_watcher.py -v

# With coverage report
pytest tests/ -v --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

**Target:** ≥80% code coverage

### Phase 2: Integration Test (7 days)

```bash
# Deploy with Docker Compose
docker-compose up -d

# Monitor logs
docker-compose logs -f bot

# Daily health checks
docker-compose exec bot python scripts/health_check.py

# Check opportunity flow
sqlite3 /data/ledger.db "SELECT COUNT(*) FROM opportunities WHERE DATE(timestamp) = DATE('now')"
```

**Target:** ≥50% of modeled opportunity flow (≥100 opportunities/day)

### Phase 3: Shadow Mode Test (14-30 days)

```bash
# Keep bot running on mainnet (no capital at risk)
docker-compose up -d

# Monitor metrics
docker-compose exec bot python scripts/health_check.py

# Check daily KPIs
sqlite3 /data/ledger.db "
SELECT date, opportunities_detected, win_rate, net_profit_usd 
FROM daily_summary 
ORDER BY date DESC 
LIMIT 7
"

# Watch logs for errors
docker-compose logs bot | grep -E "ERROR|CRITICAL|missed"
```

**Gate 0 Success Criteria:**
- ✅ Flow detected ≥50% of model (≥3K opportunities/month)
- ✅ Zero missed blocks over full period
- ✅ Ledger integrity: no corruption
- ✅ Dashboard metrics accurate

---

## 🚀 Deployment Checklist

### Before Shadow Mode

- [ ] Clone repository and checkout `develop` branch
- [ ] Create `config/bot.yaml` from `config/bot.mainnet.yaml`
- [ ] Create `.env` with Telegram tokens
- [ ] Run unit tests: `pytest tests/ -v`
- [ ] Verify config: `docker-compose config`
- [ ] Create data directory: `mkdir -p /data/logs /data/backups`

### During Deployment

- [ ] Start services: `docker-compose up -d`
- [ ] Verify algod health: `docker-compose exec algod goal node status`
- [ ] Check bot startup logs: `docker-compose logs bot | head -50`
- [ ] Run health check: `docker-compose exec bot python scripts/health_check.py`
- [ ] Set up monitoring (optional): `docker-compose up -d prometheus grafana`

### During Shadow Mode (14-30 days)

- [ ] Daily: Run `health_check.py` script
- [ ] Daily: Monitor `docker-compose logs bot`
- [ ] Weekly: Check opportunity flow vs. model
- [ ] Weekly: Review daily_summary table
- [ ] Watch for: Missed blocks, errors, negative profits

---

## 📊 Monitoring

### 1. Real-time Logs

```bash
# Follow bot logs
docker-compose logs -f bot

# Filter by level
docker-compose logs bot | grep ERROR
docker-compose logs bot | grep CRITICAL
```

### 2. Health Check Script

```bash
# Run health check
docker-compose exec bot python scripts/health_check.py

# Output:
# ✅ Database file: 50.2MB
# ✅ Ledger integrity: OK
# ✅ Recent opportunities: 156 in last 1h
# ✅ Today's KPI: 48W/100T, Win Rate: 48%, Net: $486.32
```

### 3. SQLite Queries

```bash
# Check today's opportunities
sqlite3 /data/ledger.db "
SELECT COUNT(*) as opportunities, 
       AVG(spread_bps) as avg_spread,
       MAX(spread_bps) as max_spread
FROM opportunities
WHERE DATE(timestamp) = DATE('now')
"

# Check today's KPIs
sqlite3 /data/ledger.db "
SELECT * FROM daily_summary
WHERE date = DATE('now')
"

# Check for missed blocks
sqlite3 /data/ledger.db "
SELECT * FROM (SELECT block_number FROM opportunities ORDER BY block_number DESC LIMIT 100)
WHERE (SELECT block_number FROM opportunities ORDER BY block_number DESC LIMIT 1) - block_number > 1
"
```

### 4. Optional: Prometheus + Grafana

```bash
# Enable monitoring
docker-compose --profile monitoring up -d prometheus grafana

# Access Grafana
# http://localhost:3000 (admin/admin)

# Create dashboard:
# - Data source: Prometheus (http://prometheus:9090)
# - Add panels: opportunities/hour, win_rate, net_profit
```

---

## 🐛 Troubleshooting

### Bot Won't Start

```bash
# Check logs
docker-compose logs bot

# Common issues:
# - Config file not found: cp config/bot.mainnet.yaml config/bot.yaml
# - Algod not running: docker-compose logs algod
# - Port conflicts: sudo lsof -i :4001
```

### No Opportunities Detected

```bash
# Check pool state
sqlite3 /data/ledger.db "SELECT COUNT(*) FROM opportunities WHERE DATE(timestamp) = DATE('now')"

# If 0: Check pool configuration
# - Verify pool IDs are correct
# - Check algod is synced: curl http://localhost:4001/health
# - Review bot logs for parsing errors
```

### Database Corruption

```bash
# Validate database
docker-compose exec bot python -c "
from src.ledger import Ledger
L = Ledger('/data/ledger.db')
print('Valid' if L.validate() else 'Corrupted')
"

# If corrupted:
# 1. Kill bot: docker-compose stop bot
# 2. Restore backup: cp /data/backups/latest.db /data/ledger.db
# 3. Restart: docker-compose up -d bot
```

### Missed Blocks

```bash
# Check logs for warnings
docker-compose logs bot | grep "missed"

# Check block continuity
sqlite3 /data/ledger.db "
SELECT block_number FROM opportunities
ORDER BY block_number DESC LIMIT 10
"

# If gaps found:
# - Check RPC stability
# - Increase retry logic in pool_watcher
# - Consider dedicated RPC provider (Nodely)
```

---

## 📈 Gate 0 Success Metrics

Track these metrics over 14-30 day shadow test:

| Metric | Gate 0 Target | Notes |
|--------|---------------|-------|
| **Opportunity Flow** | ≥50% of model | ≥3K per month baseline |
| **Missed Blocks** | 0 | Zero allowed |
| **Ledger Integrity** | 100% valid | No corruption detected |
| **Dashboard Accuracy** | ±5% | Metrics match live data |
| **Uptime** | ≥99% | Including RPC downtime |
| **Average Spread** | 60-80 bps | Expected range |
| **Competition Signal** | Decay <10% | Week-over-week |

---

## ✅ Gate 0 Decision

**If metrics pass:**
- ✅ Proceed to Phase 1 (live trading)
- Implement safety layers (S3.1-S3.6)
- Set up watchdog and cold wallet
- Load initial capital ($5K USDC)

**If metrics fail:**
- ⚠️ Hold at shadow mode
- Investigate root cause
- Adjust configuration or gates
- Retry shadow mode (14 days)

---

## 🔐 Security Checklist

Before loading real capital:

- [ ] All secrets in `.env` (never in code)
- [ ] SSH keys only (no password auth)
- [ ] fail2ban configured on VPS
- [ ] Encrypted backups enabled
- [ ] Cold wallet address validated
- [ ] Kill-switch tested end-to-end
- [ ] CPA engagement confirmed
- [ ] Legal review completed

---

## 📞 Support

**Deployment issues?**
- Check `docker-compose logs`
- Run `health_check.py`
- Review `SPRINT_2_README.md`

**Code issues?**
- Check test output: `pytest tests/ -v`
- Review `docs/ARCHITECTURE.md`
- Check module docstrings

**Gate 0 metrics off?**
- Check opportunity flow: expected 50%+ of model
- Check for missed blocks: should be zero
- Review logs for errors
- Validate configuration

---

## 🎯 Next Steps

1. **This week:** Deploy on testnet, run unit tests
2. **Week 2:** Deploy on mainnet in shadow mode
3. **Weeks 2-6:** Run 14-30 day shadow test (Gate 0)
4. **Week 7:** Gate 0 decision
5. **If pass:** Move to Phase 1 (live trading + safety)

---

**Deployment Ready:** ✅ July 14, 2026  
**GitHub:** https://github.com/nikhilvarma283/arbitrage  
**Branch:** develop (latest code)

**Let's deploy! 🚀**
