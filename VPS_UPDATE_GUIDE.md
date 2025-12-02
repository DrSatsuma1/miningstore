# VPS Update Guide - MinerMonitor

## Quick Reference

**VPS Login:**
```bash
ssh sats@104.223.84.214
```

**Install location:** `/miner-monitor`

---

## One-Time Setup (Private Repo)

Since this is a private repo, you need to set up git with a Personal Access Token.

### Step 1: Create a GitHub Token
1. Go to: https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Name it: `VPS access`
4. Check the **`repo`** scope
5. Click **Generate token**
6. **Copy the token** (you won't see it again!)

### Step 2: Take ownership and initialize git
```bash
sudo chown -R sats:sats /miner-monitor
cd /miner-monitor
git init
git remote add origin https://YOUR_TOKEN@github.com/DrSatsuma1/minermonitor.git
git fetch origin
git reset --hard origin/main
```

Replace `YOUR_TOKEN` with your actual token.

---

## How to Update (After Setup)

### Step 1: Pull the latest code
```bash
ssh sats@104.223.84.214
cd /miner-monitor
git pull origin main
```

### Step 2: Restart the service (if running)
```bash
# If running with systemd:
sudo systemctl restart minermonitor

# OR if running manually, kill and restart:
pkill -f miner_monitor.py
python3 miner_monitor.py &
```

That's it! The token is saved in the remote URL, so no password needed.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Permission denied` | SSH key not loaded: `ssh-add ~/.ssh/id_rsa` |
| `git pull` auth error | Token expired - create a new one and update remote |
| Find install location | `sudo find / -name "miner_monitor.py"` |

### Update the saved token (if expired)
```bash
cd /miner-monitor
git remote set-url origin https://NEW_TOKEN@github.com/DrSatsuma1/minermonitor.git
```

---

## Useful Commands

```bash
# Check if monitor is running
ps aux | grep miner_monitor

# View live logs
tail -f /miner-monitor/monitor.log

# Check service status (if using systemd)
sudo systemctl status minermonitor
```

---

**Repo:** https://github.com/DrSatsuma1/minermonitor
