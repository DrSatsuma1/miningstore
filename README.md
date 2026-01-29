# Luxor Miner Monitor

Automated monitoring script that checks your Luxor mining workers every hour and sends email alerts when miners go down.

## What This Does

1. **Every hour**: Visits your Luxor dashboard in headless Chrome (incognito mode)
2. **Scrapes**: Gets the worker count from the "Active Miners" display
3. **Compares**: Checks if count matches your expected number
4. **Waits**: Only alerts after miners have been down for 6+ hours (configurable)
5. **Alerts**: Sends professional HTML emails when miners are down
6. **Recovers**: Emails you when all miners come back online
7. **Reports**: Sends weekly uptime summary reports

## Files

| File | Purpose |
|------|---------|
| `miner_monitor.py` | Main monitoring script (heavily commented!) |
| `setup.sh` | Installs all dependencies on Linux VPS |
| `README.md` | This file |
| `VPS_UPDATE_GUIDE.md` | How to update the script on your VPS |

## Quick Start

### Step 1: Configure the Script

Open `miner_monitor.py` and update the configuration section at the top. Look for lines marked with `# <-- CHANGE THIS`:

```python
# Your Luxor watcher URL (get from Luxor dashboard > Share)
TARGET_URL = "https://app.luxor.tech/en/views/watcher?token=YOUR_TOKEN_HERE"

# How many miners should be online
EXPECTED_WORKERS = 57  # <-- CHANGE THIS

# Gmail settings
EMAIL_FROM = "YOUREMAIL@gmail.com"           # <-- CHANGE THIS
EMAIL_TO = "ALERTRECIPIENT@yourdomain.com"   # <-- CHANGE THIS
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"   # <-- CHANGE THIS

# Your info (appears in emails)
CLIENT_ID = "YOUR_CLIENT_ID"
MACHINE_TYPES = "YOUR_MACHINE_TYPES"
COMPANY_NAME = "YOUR_COMPANY_NAME"
```

### Step 2: Create Gmail App Password

You need a Gmail "App Password" (not your regular password):

1. Go to https://myaccount.google.com/security
2. Enable **2-Step Verification** if not already enabled
3. Search for **"App passwords"** in Google Account settings
4. Select "Mail" and generate a password
5. Copy the 16-character password (looks like: `xxxx xxxx xxxx xxxx`)
6. Paste it into `miner_monitor.py` as `GMAIL_APP_PASSWORD`

### Step 3: Install on VPS

Upload files to your VPS:
```bash
# Create directory
mkdir -p ~/miner-monitor
cd ~/miner-monitor

# Upload miner_monitor.py and setup.sh here (via scp, sftp, etc.)
```

Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

### Step 4: Test It

```bash
python3 miner_monitor.py
```

You should see output like:
```
==================================================
Check started at: 2025-01-28 14:30:00
==================================================
Successfully scraped worker count (Method 1): 57
Current worker count: 57
Expected worker count: 57
...
Status: OK - All miners online
==================================================
```

### Step 5: Set Up Hourly Cron Job

```bash
crontab -e
```

Add this line (replace paths with your actual paths):
```
0 * * * * cd /home/YOUR_USERNAME/miner-monitor && /usr/bin/python3 miner_monitor.py >> /home/YOUR_USERNAME/miner-monitor/monitor.log 2>&1
```

**Cron explained:**
- `0 * * * *` - Run at minute 0 of every hour
- `cd /path/to/miner-monitor` - Go to script directory
- `/usr/bin/python3 miner_monitor.py` - Run the script
- `>> monitor.log 2>&1` - Append all output to log file

## How It Works

### Alert Logic

The script uses smart alerting to avoid spam:

| Scenario | Action |
|----------|--------|
| Miners down < 6 hours | No alert (could be a reboot) |
| Miners down > 6 hours | Send first alert email |
| Still down after 24 hours | Send reminder alert |
| Miners come back online | Send recovery email |

### State Tracking

The script saves state to `miner_monitor_state.json`:
- When downtime started
- When last alert was sent
- Historical data for uptime reports

This file is created automatically - don't delete it unless you want to reset everything.

### Email Types

1. **Down Alert**: Sent when miners have been offline for 6+ hours
2. **Re-Alert**: Sent every 24 hours while miners remain down
3. **Recovery**: Sent when all miners come back online
4. **Weekly Report**: Sent every 7 days with uptime statistics

## Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `EXPECTED_WORKERS` | 57 | Number of miners that should be online |
| `DOWN_ALERT_THRESHOLD_HOURS` | 6 | Hours before first alert is sent |
| `WEEKLY_REPORT_DAYS` | 7 | Days between uptime reports |
| `HISTORY_RETENTION_DAYS` | 30 | Days of history to keep |

## Troubleshooting

### Script won't run

Check Python version:
```bash
python3 --version  # Should be 3.6+
```

### Can't scrape worker count

The Luxor page structure may have changed. Run manually to see debug output:
```bash
python3 -u miner_monitor.py
```

If all scraping methods fail, you may need to update the XPath selectors in `get_worker_count()`.

### Email not sending

Test Gmail credentials:
```bash
python3 -c "
import smtplib
s = smtplib.SMTP('smtp.gmail.com', 587)
s.starttls()
s.login('YOUREMAIL@gmail.com', 'xxxx xxxx xxxx xxxx')
print('Login successful!')
"
```

Common issues:
- Wrong App Password (not your regular Gmail password)
- 2-Step Verification not enabled
- "Less secure apps" blocked (you need an App Password)

### Check logs

```bash
# View recent log entries
tail -50 ~/miner-monitor/monitor.log

# Watch logs in real-time
tail -f ~/miner-monitor/monitor.log
```

### Chrome/ChromeDriver issues

Update ChromeDriver to match your Chrome version:
```bash
# Check Chrome version
google-chrome --version

# Download matching ChromeDriver from:
# https://chromedriver.chromium.org/downloads
```

## Security Notes

1. **Protect the script file** - it contains your Gmail App Password:
   ```bash
   chmod 600 miner_monitor.py  # Only you can read/write
   ```

2. **Don't commit to public repos** - contains credentials

3. **Gmail App Passwords** - safer than regular passwords because:
   - Can be revoked without changing your main password
   - Don't give access to your full Google account
   - Work with 2FA enabled

4. **Luxor Watcher URL** - is read-only, but still keep it private

## Manual Operations

```bash
# Force a check right now
python3 miner_monitor.py

# View current state
cat miner_monitor_state.json | python3 -m json.tool

# Reset state (will trigger new first alert if miners are down)
rm miner_monitor_state.json

# View cron jobs
crontab -l

# Check if script is running
ps aux | grep miner_monitor
```

## Support

If your hosting provider uses Jira for support, update `SUPPORT_TICKET_URL` in the script to link directly to their ticket creation page.
