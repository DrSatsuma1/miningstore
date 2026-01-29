# Luxor Miner Monitor - Multi-Dashboard Version

Automated monitoring script that checks multiple Luxor mining dashboards every hour and sends email alerts when miners go down. Each alert clearly identifies which client/site is affected.

## What This Does

1. **Every hour**: Loops through all dashboards in your config file
2. **Scrapes**: Gets the worker count from each Luxor watcher dashboard
3. **Compares**: Checks if count matches expected for each site
4. **Alerts**: Emails you with site name in subject when miners are down
5. **Recovers**: Emails when miners come back online
6. **Reports**: Sends weekly combined uptime report for all sites

## Files

- `miner_monitor.py` - Main monitoring script
- `miners.json` - Your dashboard configuration (create from example)
- `miners.example.json` - Template to copy
- `setup.sh` - Installs all dependencies
- `README.md` - This file

## Quick Setup

### 1. Create Your Config File

```bash
cp miners.example.json miners.json
```

Edit `miners.json` with your dashboards:

```json
{
  "miners": [
    {
      "name": "Client A - Main Site",
      "dashboard_url": "https://app.luxor.tech/en/views/watcher?token=YOUR_TOKEN",
      "expected_workers": 57,
      "client_id": "clienta",
      "machine_types": "S19 Pro 110T"
    },
    {
      "name": "Client B - Warehouse",
      "dashboard_url": "https://app.luxor.tech/en/views/watcher?token=ANOTHER_TOKEN",
      "expected_workers": 120,
      "client_id": "clientb",
      "machine_types": "M60S+ 202T"
    }
  ]
}
```

### Config Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Display name shown in emails (e.g., "Client A - Main Site") |
| `dashboard_url` | Yes | Luxor watcher URL with token |
| `expected_workers` | Yes | Number of miners expected to be online |
| `client_id` | No | Your Luxor client ID (for support reference) |
| `machine_types` | No | Machine model info (for support reference) |

### 2. Update Email Settings

Edit `miner_monitor.py` and update these lines:

```python
EMAIL_FROM = "your-email@gmail.com"
EMAIL_TO = "alerts@yourcompany.com"
GMAIL_APP_PASSWORD = "your app password"
```

### 3. Install Dependencies

```bash
chmod +x setup.sh
./setup.sh
```

### 4. Test

```bash
python3 miner_monitor.py
```

You should see output like:
```
============================================================
Multi-Dashboard Check started at: 2025-01-28 10:00:00
============================================================
Loaded 2 dashboard(s) from config

--- Checking: Client A - Main Site ---
Expected workers: 57
Successfully scraped worker count (Method 1): 57
Status: OK - All miners online for Client A - Main Site

--- Checking: Client B - Warehouse ---
Expected workers: 120
Successfully scraped worker count (Method 1): 118
Miners down detected. Started tracking at 2025-01-28 10:00:00
...

--- Summary: 2 succeeded, 0 failed ---
============================================================
```

### 5. Set Up Cron

```bash
crontab -e
```

Add:
```
0 * * * * cd /path/to/miner-monitor && /usr/bin/python3 miner_monitor.py >> monitor.log 2>&1
```

## How Alerts Work

### Alert Emails

Subject line includes the site name:
```
ALERT: [Client A - Main Site] 3 MINERS DOWN FOR 6 HOURS
```

Email body includes:
- Site name prominently displayed
- Expected vs actual worker count
- How long miners have been down
- Direct link to that site's dashboard
- Link to open support ticket

### Recovery Emails

```
RECOVERY: [Client A - Main Site] All Miners Back Online
```

### Weekly Reports

One combined email showing all dashboards:

| Dashboard | Workers | 7-Day | 30-Day | Status |
|-----------|---------|-------|--------|--------|
| Client A - Main Site | 57 / 57 | 99.2% | 98.5% | Online |
| Client B - Warehouse | 118 / 120 | 95.1% | 96.2% | Offline |

## State File Structure

The script stores state per-dashboard in `miner_monitor_state.json`:

```json
{
  "Client A - Main Site": {
    "last_alert_time": null,
    "last_worker_count": 57,
    "last_status": "ok",
    "down_since": null,
    "history": [...]
  },
  "Client B - Warehouse": {
    "last_alert_time": "2025-01-28T04:00:00",
    "last_worker_count": 118,
    "last_status": "down",
    "down_since": "2025-01-27T22:00:00",
    "history": [...]
  },
  "last_weekly_report": "2025-01-21T12:00:00"
}
```

## Alert Timing

- **First alert**: After 6 hours of continuous downtime (configurable)
- **Re-alerts**: Every 24 hours while miners remain down
- **Recovery**: Sent when miners come back online (only if we sent a down alert)

This avoids alert spam from brief outages (reboots, network blips).

## Adding a New Dashboard

1. Get the Luxor watcher URL (Dashboard > Watcher > Share link)
2. Add entry to `miners.json`:
   ```json
   {
     "name": "New Client - Location",
     "dashboard_url": "https://app.luxor.tech/en/views/watcher?token=NEW_TOKEN",
     "expected_workers": 50
   }
   ```
3. Script will pick it up on next run

## Troubleshooting

### Config file not found
```
CONFIG ERROR: Config file not found: /path/to/miners.json
Copy miners.example.json to miners.json and add your dashboards.
```

### One dashboard fails but others work
The script continues checking remaining dashboards. Check the log for the specific error.

### Check logs
```bash
tail -f monitor.log
```

## Security

- `miners.json` contains dashboard tokens - don't commit to git
- Already in `.gitignore`
- Protect with: `chmod 600 miners.json miner_monitor.py`
