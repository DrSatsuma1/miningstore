# VPS Update Guide - MinerMonitor

## Quick Reference

**VPS Login:**
```bash
ssh sats@104.223.84.214
```

---

## First-Time Install (Do This First!)

If you don't see a `minermonitor` folder when you run `ls`, you need to install it:

```bash
git clone https://github.com/DrSatsuma1/minermonitor.git
cd minermonitor
chmod +x setup.sh
./setup.sh
python3 miner_monitor.py
```

---

## How to Update the Software

### Step 1: Connect to your VPS
```bash
ssh sats@104.223.84.214
```

### Step 2: Navigate to the project folder
```bash
cd ~/minermonitor
```
*(Adjust path if you installed it elsewhere)*

### Step 3: Pull the latest code
```bash
git pull origin main
```

### Step 4: Restart the service (if running)
```bash
# If running with systemd:
sudo systemctl restart minermonitor

# OR if running manually, kill and restart:
pkill -f miner_monitor.py
python3 miner_monitor.py &
```

---

## One-Liner Update (Copy & Paste)

```bash
ssh sats@104.223.84.214 "cd ~/minermonitor && git pull origin main && sudo systemctl restart minermonitor"
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Permission denied` | Make sure your SSH key is loaded: `ssh-add ~/.ssh/id_rsa` |
| `git pull` fails | Check internet: `ping github.com` |
| Service won't start | Check logs: `journalctl -u minermonitor -f` |
| Manual process check | `ps aux \| grep miner_monitor` |

---

## Useful Commands

```bash
# Check if monitor is running
ps aux | grep miner_monitor

# View live logs
tail -f ~/minermonitor/monitor.log

# Check service status
sudo systemctl status minermonitor

# View recent errors
journalctl -u minermonitor --since "1 hour ago"
```

---

**Repo:** https://github.com/DrSatsuma1/minermonitor
