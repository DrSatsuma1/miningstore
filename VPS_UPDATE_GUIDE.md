# VPS Update Guide - MinerMonitor

This guide explains how to update the miner monitor script on your VPS after making changes.

## Quick Reference

**VPS Login:**
```bash
ssh YOUR_USERNAME@YOUR_VPS_IP_ADDRESS
```

**Install location:** `/home/YOUR_USERNAME/miner-monitor` (or wherever you installed it)

---

## Option 1: Manual File Update (Simplest)

If you're not using git, just re-upload the changed files:

### Using SCP (from your local machine):
```bash
scp miner_monitor.py YOUR_USERNAME@YOUR_VPS_IP:/home/YOUR_USERNAME/miner-monitor/
```

### Using SFTP:
```bash
sftp YOUR_USERNAME@YOUR_VPS_IP
put miner_monitor.py /home/YOUR_USERNAME/miner-monitor/
exit
```

---

## Option 2: Using Git (Recommended for Multiple Updates)

If you've set up a git repository, updates are easier.

### One-Time Setup (Private Repo)

If this is a private repo, you need a Personal Access Token.

**Step 1: Create a GitHub Token**
1. Go to: https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Name it: `VPS access`
4. Check the **`repo`** scope
5. Click **Generate token**
6. **Copy the token** (you won't see it again!)

**Step 2: Initialize git on VPS**
```bash
cd /home/YOUR_USERNAME/miner-monitor
git init
git remote add origin https://YOUR_TOKEN@github.com/YOUR_GITHUB_USERNAME/minermonitor.git
git fetch origin
git reset --hard origin/main
```

Replace:
- `YOUR_TOKEN` with your actual GitHub token
- `YOUR_GITHUB_USERNAME` with your GitHub username

### Pulling Updates

Once git is set up, updating is simple:

```bash
ssh YOUR_USERNAME@YOUR_VPS_IP
cd /home/YOUR_USERNAME/miner-monitor
git pull origin main
```

That's it! The token is saved in the remote URL, so no password needed.

---

## After Updating

The script runs via cron, so it will automatically use the new version on the next hourly run.

If you want to test immediately:
```bash
python3 miner_monitor.py
```

If you're running the script as a systemd service:
```bash
sudo systemctl restart minermonitor
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Permission denied` | Check file ownership: `sudo chown YOUR_USERNAME:YOUR_USERNAME miner_monitor.py` |
| `git pull` auth error | Token expired - create a new one and update remote (see below) |
| Find install location | `find ~ -name "miner_monitor.py"` |

### Update the saved token (if expired)
```bash
cd /home/YOUR_USERNAME/miner-monitor
git remote set-url origin https://NEW_TOKEN@github.com/YOUR_GITHUB_USERNAME/minermonitor.git
```

---

## Useful Commands

```bash
# Check if monitor is running
ps aux | grep miner_monitor

# View live logs
tail -f /home/YOUR_USERNAME/miner-monitor/monitor.log

# View last 50 log lines
tail -50 /home/YOUR_USERNAME/miner-monitor/monitor.log

# Check cron job
crontab -l

# Edit cron job
crontab -e
```

---

## Placeholders to Replace

Throughout this guide, replace these placeholders with your actual values:

| Placeholder | Example | Description |
|-------------|---------|-------------|
| `YOUR_USERNAME` | `ubuntu` | Your VPS login username |
| `YOUR_VPS_IP` | `192.168.1.100` | Your VPS IP address |
| `YOUR_TOKEN` | `ghp_xxxx...` | GitHub Personal Access Token |
| `YOUR_GITHUB_USERNAME` | `johndoe` | Your GitHub username |
