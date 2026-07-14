# Arbitrage Bot - VPS Deployment Guide for Automated Agent

**Status:** Production Deployment Ready  
**Version:** Sprint 2 Complete  
**Date:** July 14, 2026  
**Repository:** https://github.com/nikhilvarma283/arbitrage  
**Branch:** develop  

---

## 📋 DEPLOYMENT PREREQUISITES CHECKLIST

### VPS Access Details
Agent should collect/verify:
- [ ] VPS IP address or hostname
- [ ] SSH port (default 22)
- [ ] SSH username (typically `ubuntu`, `ec2-user`, or `root`)
- [ ] SSH authentication method (private key path)
- [ ] Private key has correct permissions (`chmod 600`)

### VPS Environment Requirements
Agent should verify:
- [ ] Operating System: Ubuntu 24.04 LTS (or 20.04+, CentOS 7+)
- [ ] Python 3.11+ installed (if not, agent will install)
- [ ] Git installed (if not, agent will install)
- [ ] Sudo access available (for package installation)
- [ ] Firewall allows outbound HTTPS (for GitHub, Docker Hub)
- [ ] At least 240GB free disk space
- [ ] At least 16GB RAM available
- [ ] At least 8 vCPU cores available

### Deployment Configuration
Agent must collect:
- [ ] GitHub repository URL: `https://github.com/nikhilvarma283/arbitrage`
- [ ] Deploy branch: `develop` (contains all Sprint 2 code)
- [ ] Telegram Bot Token (from @BotFather)
- [ ] Telegram Chat ID (from @userinfobot)
- [ ] Algorand node: Local `algod` in Docker OR remote RPC (Nodely/AlgoNode)
- [ ] Hot wallet address (if available, optional for shadow mode)
- [ ] Cold wallet address (if available, optional)

### Deployment Scope
Agent should confirm with user:
- [ ] Deploy bot application (mandatory)
- [ ] Set up systemd services for auto-restart (recommended)
- [ ] Configure logging and monitoring (recommended)
- [ ] Enable Telegram alerts (recommended)
- [ ] Setup health check monitoring (recommended)

---

## 🚀 AUTOMATED DEPLOYMENT STEPS

### Phase 1: System Preparation (Agent-Executed)

#### 1.1 SSH Connection & Verification
```bash
# Connect to VPS
ssh -i $SSH_KEY_PATH $SSH_USER@$VPS_IP -p $SSH_PORT

# Verify OS and resources
uname -a
lsb_release -a
free -h
df -h /
nproc
```

**Agent should verify:**
- Linux/Ubuntu OS detected
- Python 3.11+ available
- At least 16GB RAM free
- At least 100GB disk free

#### 1.2 Install System Dependencies (if needed)
```bash
# Update package manager
sudo apt update && sudo apt upgrade -y

# Install essential tools
sudo apt install -y \
    git \
    curl \
    wget \
    htop \
    tmux \
    build-essential \
    python3.11 \
    python3.11-venv \
    python3.11-dev

# Verify installations
git --version
python3.11 --version
```

#### 1.3 Install Docker & Docker Compose
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
rm get-docker.sh

# Add user to docker group (so no sudo needed)
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installations
docker --version
docker-compose --version
docker ps  # Should work without sudo
```

#### 1.4 Create Application Directory
```bash
# Create app directory
mkdir -p /home/$USER/arbitrage/data/logs
mkdir -p /home/$USER/arbitrage/data/backups
cd /home/$USER/arbitrage

# Set permissions
chmod 755 data/
chmod 755 data/logs/
chmod 755 data/backups/
```

---

### Phase 2: Repository Setup (Agent-Executed)

#### 2.1 Clone Repository
```bash
cd /home/$USER/arbitrage

# Clone repository
git clone https://github.com/nikhilvarma283/arbitrage.git .
git fetch origin develop
git checkout develop
git pull origin develop

# Verify branch
git branch -a
git log --oneline -5
```

**Agent should verify:**
- Repository cloned successfully
- Develop branch checked out
- Latest commits present (should include Sprint 2 code)

#### 2.2 Verify Repository Structure
```bash
# Check key files exist
test -f docker-compose.yml && echo "✓ docker-compose.yml" || echo "✗ Missing docker-compose.yml"
test -f Dockerfile && echo "✓ Dockerfile" || echo "✗ Missing Dockerfile"
test -f requirements.txt && echo "✓ requirements.txt" || echo "✗ Missing requirements.txt"
test -d src/ && echo "✓ src/ directory" || echo "✗ Missing src/ directory"
test -d config/ && echo "✓ config/ directory" || echo "✗ Missing config/ directory"
test -d scripts/ && echo "✓ scripts/ directory" || echo "✗ Missing scripts/ directory"

# List core modules
ls -lh src/*.py
```

**Agent should verify:**
- All key files present
- All core modules present (main.py, pool_watcher.py, opportunity_engine.py, ledger.py, alerts.py)

---

### Phase 3: Configuration Setup (Agent-Executed)

#### 3.1 Create bot.yaml from Template
```bash
cd /home/$USER/arbitrage/config

# Copy template
cp bot.mainnet.yaml bot.yaml

# Verify file created
test -f bot.yaml && echo "✓ bot.yaml created" || echo "✗ Failed to create bot.yaml"
```

#### 3.2 Create .env File with Secrets
```bash
cd /home/$USER/arbitrage

# Create .env with provided secrets
cat > .env << 'EOF'
# Telegram Configuration (REQUIRED)
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}

# Algorand Configuration (Optional - defaults to local)
ALGOD_HOST=algod
ALGOD_PORT=4001
ALGOD_TOKEN=

# Wallet Configuration (Optional for shadow mode)
HOT_WALLET_ADDRESS=${HOT_WALLET_ADDRESS:-}
COLD_WALLET_ADDRESS=${COLD_WALLET_ADDRESS:-}

# Application Configuration
APP_MODE=shadow
LOG_LEVEL=INFO
LOG_FILE=/data/logs/bot.log
EOF

# Restrict permissions (CRITICAL for security)
chmod 600 .env
chmod 600 config/bot.yaml

# Verify permissions
ls -l .env
ls -l config/bot.yaml
```

**Agent should verify:**
- .env file created with correct permissions (600)
- All required secrets present
- Secrets are NOT logged or echoed to console

#### 3.3 Validate Configuration
```bash
# Check YAML syntax
python3.11 -c "import yaml; yaml.safe_load(open('config/bot.yaml'))" && echo "✓ bot.yaml is valid" || echo "✗ bot.yaml has syntax errors"

# Check .env file
test -f .env && echo "✓ .env exists" || echo "✗ .env missing"
grep -q "TELEGRAM_BOT_TOKEN" .env && echo "✓ Telegram token present" || echo "✗ Telegram token missing"
```

---

### Phase 4: Docker Setup & Deployment (Agent-Executed)

#### 4.1 Build Docker Images
```bash
cd /home/$USER/arbitrage

# Pull base images
docker pull python:3.11-slim
docker pull algorand/algod:latest

# Build bot image
docker-compose build --no-cache

# Verify images built
docker images | grep arbitrage
```

**Agent should verify:**
- Bot image successfully built
- No build errors

#### 4.2 Start Services
```bash
cd /home/$USER/arbitrage

# Start services (detached mode)
docker-compose up -d

# Wait for services to start
sleep 10

# Check service status
docker-compose ps

# Verify all services are running
docker-compose ps --services --filter "status=running"
```

**Agent should verify:**
- All services running (algod, bot, optionally prometheus/grafana)
- No services exited with error

#### 4.3 Verify Services Are Healthy
```bash
# Check algod health
docker-compose exec algod curl -s http://localhost:4001/health || echo "Algod not ready yet"

# Check bot logs for startup
docker-compose logs bot --tail=50

# Wait for algod to sync (can take a few minutes)
echo "Waiting for Algorand node to sync..."
for i in {1..60}; do
    if docker-compose exec algod goal node status 2>/dev/null | grep -q "Sync Time: 0"; then
        echo "✓ Algorand node synced!"
        break
    fi
    echo "  Syncing... ($i/60)"
    sleep 5
done
```

**Agent should verify:**
- Algod health endpoint responds
- Bot logs show no critical errors
- Algod is synced to mainnet

#### 4.4 Health Check
```bash
# Run health check script
docker-compose exec bot python scripts/health_check.py

# Check database
docker-compose exec bot ls -lh /data/ledger.db

# Verify logs directory
docker-compose exec bot ls -lh /data/logs/
```

**Agent should verify:**
- Health check passes
- Database created
- Logs being written

---

### Phase 5: Systemd Setup (Agent-Executed, Optional)

#### 5.1 Create Systemd Service File
```bash
# Create service file
sudo tee /etc/systemd/system/arbitrage-bot.service > /dev/null << 'EOF'
[Unit]
Description=Arbitrage Bot Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=$USER
WorkingDirectory=/home/$USER/arbitrage
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable arbitrage-bot.service
sudo systemctl start arbitrage-bot.service

# Check service status
sudo systemctl status arbitrage-bot.service

# View service logs
sudo journalctl -u arbitrage-bot.service -n 20
```

#### 5.2 Create Monitoring Script
```bash
# Create monitoring script
mkdir -p /home/$USER/arbitrage/monitoring

cat > /home/$USER/arbitrage/monitoring/watch.sh << 'EOF'
#!/bin/bash
cd /home/$USER/arbitrage

echo "=== Arbitrage Bot Monitor ==="
echo "Time: $(date)"
echo ""

echo "Service Status:"
sudo systemctl status arbitrage-bot.service --no-pager | head -5

echo ""
echo "Docker Status:"
docker-compose ps

echo ""
echo "Recent Bot Logs:"
docker-compose logs bot --tail=10

echo ""
echo "Health Check:"
docker-compose exec bot python scripts/health_check.py 2>/dev/null || echo "Health check failed or bot not ready"

echo ""
echo "Database Size:"
docker-compose exec bot ls -lh /data/ledger.db 2>/dev/null || echo "Database not found"

echo ""
echo "Disk Usage:"
df -h /

echo ""
echo "Memory Usage:"
free -h
EOF

chmod +x /home/$USER/arbitrage/monitoring/watch.sh
```

---

### Phase 6: Verification & Testing (Agent-Executed)

#### 6.1 Comprehensive Health Check
```bash
cd /home/$USER/arbitrage

echo "=== DEPLOYMENT VERIFICATION ==="
echo ""

# 1. Check Docker
echo "[1/6] Docker Status:"
docker-compose ps
echo "Status: $(docker-compose ps --services --filter 'status=running' | wc -l) services running"

# 2. Check Algod
echo ""
echo "[2/6] Algorand Node Status:"
docker-compose exec algod goal node status || echo "Algod not synced"

# 3. Check Bot Startup
echo ""
echo "[3/6] Bot Startup Logs:"
docker-compose logs bot --tail=20 | tail -5

# 4. Check Database
echo ""
echo "[4/6] Database Status:"
docker-compose exec bot python -c "
from src.ledger import Ledger
L = Ledger('/data/ledger.db')
print('✓ Database accessible')
print('✓ Integrity check: PASS' if L.validate() else '✗ Integrity check: FAIL')
" 2>/dev/null || echo "Database check failed"

# 5. Check Telegram Connection
echo ""
echo "[5/6] Telegram Configuration:"
grep -q "TELEGRAM_BOT_TOKEN" .env && echo "✓ Telegram token configured" || echo "✗ Telegram token missing"

# 6. Check File Permissions
echo ""
echo "[6/6] File Permissions:"
ls -l .env | grep -q "600" && echo "✓ .env permissions correct (600)" || echo "✗ .env permissions incorrect"
ls -l config/bot.yaml | grep -q "600" && echo "✓ bot.yaml permissions correct (600)" || echo "✗ bot.yaml permissions incorrect"
```

#### 6.2 Run Unit Tests (Optional)
```bash
cd /home/$USER/arbitrage

# Install test dependencies
docker-compose exec bot pip install pytest pytest-cov

# Run tests
docker-compose exec bot pytest tests/ -v --tb=short

# Run coverage
docker-compose exec bot pytest tests/ --cov=src --cov-report=term-missing
```

#### 6.3 Test Telegram Alerts
```bash
# Send test alert
docker-compose exec bot python -c "
from src.alerts import AlertManager
alerts = AlertManager('$TELEGRAM_BOT_TOKEN', '$TELEGRAM_CHAT_ID')
result = alerts.send_error('Test alert from deployment', 'warning')
print(f'Alert sent: {result}')
"
```

**Agent should verify:**
- Test alert received in Telegram chat

---

### Phase 7: Post-Deployment Configuration (Agent-Executed)

#### 7.1 Set Up Log Rotation
```bash
# Create logrotate configuration
sudo tee /etc/logrotate.d/arbitrage-bot > /dev/null << 'EOF'
/home/$USER/arbitrage/data/logs/*.log {
    daily
    rotate 10
    compress
    delaycompress
    notifempty
    create 0640 $USER $USER
    sharedscripts
}
EOF

# Test logrotate
sudo logrotate -d /etc/logrotate.d/arbitrage-bot
```

#### 7.2 Set Up Backup Script
```bash
# Create backup script
mkdir -p /home/$USER/arbitrage/scripts

cat > /home/$USER/arbitrage/scripts/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/home/$USER/arbitrage/data/backups
DATE=$(date +%Y%m%d_%H%M%S)

# Backup ledger database
docker-compose exec -T bot cp /data/ledger.db $BACKUP_DIR/ledger_$DATE.db

# Compress backup
gzip $BACKUP_DIR/ledger_$DATE.db

# Keep only last 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/ledger_$DATE.db.gz"
EOF

chmod +x /home/$USER/arbitrage/scripts/backup.sh

# Add to crontab (run daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /home/$USER/arbitrage/scripts/backup.sh") | crontab -
```

#### 7.3 Set Up Monitoring Cron Job
```bash
# Add monitoring check to crontab (every 15 minutes)
(crontab -l 2>/dev/null; echo "*/15 * * * * /home/$USER/arbitrage/monitoring/watch.sh >> /home/$USER/arbitrage/data/logs/monitor.log 2>&1") | crontab -

# Verify crontab
crontab -l
```

---

## 📊 DEPLOYMENT VERIFICATION CHECKLIST

After deployment, agent should verify:

### Services Running
- [ ] `docker-compose ps` shows all services as "Up"
- [ ] Algod container is synced to mainnet
- [ ] Bot container is running

### Configuration
- [ ] `.env` file exists with correct permissions (600)
- [ ] `config/bot.yaml` created with correct permissions (600)
- [ ] Telegram token configured in `.env`
- [ ] Telegram Chat ID configured in `.env`

### Database
- [ ] `/data/ledger.db` exists and is accessible
- [ ] Database integrity check passes
- [ ] `/data/logs/bot.log` is being written to

### Monitoring
- [ ] Systemd service running (if configured)
- [ ] Health check script executes successfully
- [ ] Monitoring script executes without errors

### Telegram Integration
- [ ] Test alert sent and received in Telegram chat
- [ ] Alert formatting is readable

---

## 🎯 SHADOW MODE STARTUP

Once deployment is complete and verified:

```bash
cd /home/$USER/arbitrage

# View bot logs in real-time
docker-compose logs -f bot

# Expected startup sequence:
# 1. Bot initializes (2-3 seconds)
# 2. Connects to algod (5-10 seconds)
# 3. Starts pool watching
# 4. Detects opportunities
# 5. Logs to database

# Check daily summary
docker-compose exec bot sqlite3 /data/ledger.db "SELECT * FROM daily_summary LIMIT 1;"
```

---

## 🔧 TROUBLESHOOTING

### If Services Won't Start
```bash
# Check logs
docker-compose logs

# Check docker daemon
sudo systemctl status docker

# Restart docker
sudo systemctl restart docker
docker-compose up -d
```

### If Algod Won't Sync
```bash
# Check algod status
docker-compose exec algod goal node status

# View algod logs
docker-compose logs algod --tail=50

# Restart algod
docker-compose restart algod

# Wait for sync (can take several minutes)
```

### If Bot Crashes
```bash
# View detailed logs
docker-compose logs bot --tail=100

# Check database
docker-compose exec bot sqlite3 /data/ledger.db ".tables"

# Restart bot
docker-compose restart bot
```

### If Telegram Alerts Don't Work
```bash
# Verify token and chat ID
grep TELEGRAM .env

# Test Telegram connection
docker-compose exec bot python -c "
import requests
response = requests.get('https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe')
print(response.json())
"
```

---

## 📈 NEXT STEPS AFTER DEPLOYMENT

1. **Monitor Shadow Mode (14-30 days)**
   - Watch opportunity detection
   - Monitor for missed blocks
   - Track KPIs vs. model predictions

2. **Gate 0 Validation**
   - Check if flow ≥50% of model (≥3K/month)
   - Verify zero missed blocks
   - Confirm ledger integrity

3. **Gate 0 Decision**
   - If PASS → Proceed to Phase 1 (live trading)
   - If FAIL → Adjust configuration, retry

---

## 📞 SUPPORT & MONITORING

**Monitor bot daily:**
```bash
/home/$USER/arbitrage/monitoring/watch.sh
```

**View recent logs:**
```bash
docker-compose logs bot --tail=50
```

**Check health:**
```bash
docker-compose exec bot python scripts/health_check.py
```

**Emergency restart:**
```bash
docker-compose restart bot
```

**Emergency halt:**
```bash
docker-compose stop bot
```

---

**Deployment Status:** ✅ READY  
**Repository:** https://github.com/nikhilvarma283/arbitrage  
**Branch:** develop  
**Last Updated:** July 14, 2026
