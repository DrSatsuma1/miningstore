# Luxor Miner Monitor

Automated monitoring script that checks your Luxor mining workers every hour and sends email alerts when miners go down.

## What This Does

1. **Every hour**: Visits your Luxor dashboard in headless Chrome (incognito mode)
2. **Scrapes**: Gets the worker count from the green checkmark number
3. **Compares**: Checks if count equals 57 (your expected number)
4. **Alerts**: Emails you if miners are down
5. **Recovers**: Emails when all miners come back online

## Files

- `miner_monitor.py` - Main monitoring script
- `setup.sh` - Installs all dependencies
- `README.md` - This file

## Installation on Your VPS

### Step 1: Upload Files

Upload these files to your VPS in a directory like `/home/yourusername/miner-monitor/`

```bash
# Create directory
mkdir -p ~/miner-monitor
cd ~/miner-monitor

# Upload miner_monitor.py and setup.sh here
```

### Step 2: Run Setup Script

```bash
chmod +x setup.sh
./setup.sh
```

This installs:
- Python3 and pip
- Google Chrome (headless browser)
- ChromeDriver (Selenium controller)
- Selenium Python package

### Step 3: Make Script Executable

```bash
chmod +x miner_monitor.py
```

### Step 4: Test the Script

Run it manually to verify it works:

```bash
python3 miner_monitor.py
```

You should see output like:
```
==================================================
Check started at: 2025-10-23 20:30:00
==================================================
Successfully scraped worker count: 56
Current worker count: 56
Expected worker count: 57
...
Email sent: ALERT 1 MINER DOWN
==================================================
```

### Step 5: Set Up Hourly Cron Job

Edit your crontab:

```bash
crontab -e
```

Add this line (replace `/home/yourusername` with your actual path):

```
0 * * * * cd /home/yourusername/miner-monitor && /usr/bin/python3 miner_monitor.py >> /home/yourusername/miner-monitor/monitor.log 2>&1
```

**What this means:**
- `0 * * * *` - Run at minute 0 of every hour
- `cd /home/yourusername/miner-monitor` - Go to script directory
- `/usr/bin/python3 miner_monitor.py` - Run the script
- `>> monitor.log 2>&1` - Save all output to monitor.log file

Save and exit (Ctrl+X, then Y, then Enter in nano).

### Step 6: Verify Cron Job

Check that cron job was added:

```bash
crontab -l
```

## How It Works

### State Tracking
The script saves state to `miner_monitor_state.json` in the same directory as the script:
- Last worker count
- When it last sent an alert
- Current status (ok/down/unknown)

### Alert Logic

**When miners go down (count < 57):**
- Sends alert email: "ALERT X MINER DOWN"
- Won't send another alert for 12 hours (cooldown period)
- Continues monitoring but suppresses duplicate alerts

**When miners recover (count returns to 57):**
- Sends recovery email: "RECOVERY - All Miners Back Online"
- Resets alert status

**If count > 57:**
- No alert (you only care about down miners)
- Logs as INFO

### Email Sending

Uses Gmail's SMTP server:
- Server: smtp.gmail.com:587
- Protocol: STARTTLS (encrypted)
- Authentication: App Password (not your regular Gmail password)

The app password is stored in the script. Gmail requires app passwords for scripts because they're more secure than using your main password.

## Troubleshooting

### Script fails to run

Check Python version:
```bash
python3 --version  # Should be 3.6+
```

### Can't scrape worker count

The page might have changed its structure. Run manually with more verbose output:
```bash
python3 -u miner_monitor.py
```

### Email not sending

Test Gmail credentials:
```bash
python3 -c "import smtplib; s=smtplib.SMTP('smtp.gmail.com',587); s.starttls(); s.login('codegraymining@gmail.com','oqal afxf qjth purb'); print('Login successful')"
```

### Check logs

View recent cron executions:
```bash
tail -f ~/miner-monitor/monitor.log
```

### Chrome/ChromeDriver issues

Update ChromeDriver:
```bash
# Get latest version
CHROME_DRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE)
wget https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip
unzip chromedriver_linux64.zip
sudo mv chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver
```

## Manual Testing

Test different scenarios:

```bash
# Normal run
python3 miner_monitor.py

# Check state file (in same directory as script)
cat miner_monitor_state.json

# Reset state (force new alert)
rm miner_monitor_state.json
python3 miner_monitor.py
```

## Configuration Changes

To modify settings, edit `miner_monitor.py`:

```python
EXPECTED_WORKERS = 57  # Change expected count
ALERT_COOLDOWN_HOURS = 12  # Change cooldown period
EMAIL_TO = "cstott@gmail.com"  # Change alert email
```

## Security Note

The script contains your Gmail app password. Protect this file:

```bash
chmod 600 miner_monitor.py  # Only you can read/write
```

Don't commit this file to public repositories.
