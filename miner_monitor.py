#!/usr/bin/env python3
"""
Luxor Mining Worker Monitor - Multi-Dashboard Version

This script monitors multiple Bitcoin mining dashboards via the Luxor mining pool.
It runs hourly (via cron) to check if all expected miners are online across all
configured dashboards, and sends email alerts when miners go down.

Key Features:
- Monitors multiple Luxor dashboards from a single config file (miners.json)
- Each dashboard has its own expected worker count and state tracking
- Alerts clearly identify which client/site is affected
- Combined weekly uptime report for all dashboards
- Continues checking other dashboards if one fails

Configuration:
- Copy miners.example.json to miners.json
- Add your dashboard URLs and expected worker counts
- Set email credentials below

Typical cron setup (runs every hour):
    0 * * * * /usr/bin/python3 /path/to/miner_monitor.py >> /path/to/monitor.log 2>&1
"""

import fcntl
import json
import os
import smtplib
import sys
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =============================================================================
# CONFIGURATION - Update these settings for your setup
# =============================================================================

# Config file containing all dashboard entries
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miners.json")

# Email settings - Uses Gmail SMTP with an "App Password" (not your regular password)
# To create an App Password: Google Account > Security > 2-Step Verification > App Passwords
EMAIL_FROM = "codegraymining@gmail.com"  # Gmail address to send from
EMAIL_TO = "cstott@gmail.com"            # Recipient for alerts
GMAIL_APP_PASSWORD = "oqal afxf qjth purb"  # Gmail App Password (16 chars, spaces ok)

# State and lock files - stored in same directory as script
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miner_monitor_state.json")
LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miner_monitor.lock")

# Alert timing settings
DOWN_ALERT_THRESHOLD_HOURS = 6  # Only alert after miner is down for this many hours
WEEKLY_REPORT_DAYS = 7          # Send uptime report every N days
HISTORY_RETENTION_DAYS = 30     # Keep N days of history for uptime calculations

# Jira Service Desk URL - Direct link to create a support ticket
SUPPORT_TICKET_URL = "https://miningstore.atlassian.net/servicedesk/customer/portal/1/group/4/create/18"


# =============================================================================
# CONFIG FILE LOADING
# =============================================================================

def load_config():
    """
    Load dashboard configuration from miners.json.

    Returns:
        list: Array of miner configurations, each containing:
            - name: Display name for this dashboard (e.g., "Client A - Main Site")
            - dashboard_url: Luxor watcher URL with token
            - expected_workers: Number of miners expected to be online
            - client_id: Short identifier (for support reference)
            - machine_types: Machine model info (for support reference)

    Raises:
        FileNotFoundError: If miners.json doesn't exist
        ValueError: If config is missing required fields
    """
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_FILE}\n"
            f"Copy miners.example.json to miners.json and add your dashboards."
        )

    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    if 'miners' not in config or not config['miners']:
        raise ValueError("Config file must contain a 'miners' array with at least one entry")

    # Validate required fields
    required_fields = ['name', 'dashboard_url', 'expected_workers']
    for i, miner in enumerate(config['miners']):
        for field in required_fields:
            if field not in miner:
                raise ValueError(f"Miner entry {i} missing required field: {field}")

    return config['miners']


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_duration(hours):
    """Format hours as 'X hours Y minutes' or 'X minutes' if less than 1 hour"""
    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    if h == 0:
        return f"{m} minute{'s' if m != 1 else ''}"
    elif m == 0:
        return f"{h} hour{'s' if h != 1 else ''}"
    else:
        return f"{h} hour{'s' if h != 1 else ''} {m} minute{'s' if m != 1 else ''}"


# =============================================================================
# STATE MANAGEMENT
# =============================================================================
# State is now stored per-dashboard using the dashboard name as key:
# {
#   "Client A - Main Site": {
#     "last_alert_time": "...",
#     "last_worker_count": 57,
#     "last_status": "ok",
#     "down_since": null,
#     "history": [...]
#   },
#   "Client B - Warehouse": { ... },
#   "last_weekly_report": "..."  # Global, not per-dashboard
# }

def load_state():
    """Load monitoring state from file, with per-dashboard structure."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_state(state):
    """Save monitoring state to file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def get_dashboard_state(state, name):
    """
    Get or initialize state for a specific dashboard.

    Args:
        state: The full state dictionary
        name: Dashboard name (key)

    Returns:
        dict: State for this dashboard with all required fields
    """
    default = {
        'last_alert_time': None,
        'last_worker_count': None,
        'last_status': 'unknown',
        'down_since': None,
        'history': []
    }

    if name not in state:
        state[name] = default
    else:
        # Ensure all fields exist (backward compatibility)
        for key, value in default.items():
            if key not in state[name]:
                state[name][key] = value

    return state[name]


def clean_old_history(dashboard_state, current_time):
    """Remove history entries older than HISTORY_RETENTION_DAYS"""
    cutoff_time = current_time - timedelta(days=HISTORY_RETENTION_DAYS)
    dashboard_state['history'] = [
        entry for entry in dashboard_state['history']
        if datetime.fromisoformat(entry['timestamp']) > cutoff_time
    ]


def add_history_entry(dashboard_state, timestamp, worker_count, status):
    """Add a new history entry for a dashboard"""
    dashboard_state['history'].append({
        'timestamp': timestamp.isoformat(),
        'worker_count': worker_count,
        'status': status
    })


# =============================================================================
# EMAIL SENDING
# =============================================================================

def send_email(subject, body):
    """Send email via Gmail SMTP"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)

        server.send_message(msg)
        server.quit()

        print(f"Email sent: {subject}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


# =============================================================================
# UPTIME CALCULATION
# =============================================================================

def calculate_uptime_percentage(dashboard_state, expected_workers, days):
    """
    Calculate uptime percentage for a dashboard over the last N days.

    Args:
        dashboard_state: State dict for this dashboard
        expected_workers: Expected worker count for this dashboard
        days: Number of days to calculate uptime for

    Returns:
        Float percentage (0-100) or None if insufficient data
    """
    if not dashboard_state['history']:
        return None

    current_time = datetime.now()
    cutoff_time = current_time - timedelta(days=days)

    relevant_history = [
        entry for entry in dashboard_state['history']
        if datetime.fromisoformat(entry['timestamp']) > cutoff_time
    ]

    if not relevant_history:
        return None

    up_count = sum(1 for entry in relevant_history
                   if entry['worker_count'] >= expected_workers)
    total_count = len(relevant_history)

    if total_count == 0:
        return None

    return (up_count / total_count) * 100


# =============================================================================
# WEEKLY REPORTS
# =============================================================================

def send_weekly_report(state, miners_config):
    """
    Send combined weekly uptime report for all dashboards.

    Creates a single email with a table showing uptime stats for each
    monitored dashboard.
    """
    current_time = datetime.now()

    # Build table rows for each dashboard
    table_rows = ""
    for miner in miners_config:
        name = miner['name']
        expected = miner['expected_workers']
        dashboard_state = get_dashboard_state(state, name)

        uptime_7d = calculate_uptime_percentage(dashboard_state, expected, 7)
        uptime_30d = calculate_uptime_percentage(dashboard_state, expected, 30)

        uptime_7d_str = f"{uptime_7d:.1f}%" if uptime_7d is not None else "N/A"
        uptime_30d_str = f"{uptime_30d:.1f}%" if uptime_30d is not None else "N/A"

        status = dashboard_state.get('last_status', 'unknown')
        status_color = "#27ae60" if status == 'ok' else "#d4a017" if status == 'down' else "#95a5a6"
        status_text = "Online" if status == 'ok' else "Offline" if status == 'down' else "Unknown"

        last_count = dashboard_state.get('last_worker_count', 'N/A')

        table_rows += f"""
                                <tr>
                                    <td style="padding: 12px 15px; border-bottom: 1px solid #f1f1f1; font-weight: 500;">{name}</td>
                                    <td align="center" style="padding: 12px 15px; border-bottom: 1px solid #f1f1f1;">{last_count} / {expected}</td>
                                    <td align="center" style="padding: 12px 15px; border-bottom: 1px solid #f1f1f1;">{uptime_7d_str}</td>
                                    <td align="center" style="padding: 12px 15px; border-bottom: 1px solid #f1f1f1;">{uptime_30d_str}</td>
                                    <td align="center" style="padding: 12px 15px; border-bottom: 1px solid #f1f1f1; color: {status_color}; font-weight: bold;">{status_text}</td>
                                </tr>"""

    subject = "Weekly Miner Uptime Report - All Dashboards"

    body = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="margin: 0; padding: 0; background-color: #f8f9fa; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8f9fa; padding: 40px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="700" style="background-color: #ffffff; border: 1px solid #e0e0e0; border-collapse: collapse;">
                    <!-- Header -->
                    <tr>
                        <td align="left" style="background-color: #1a2b3c; padding: 35px 30px;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 500; letter-spacing: 0.5px;">Weekly Uptime Report</h1>
                            <p style="margin: 8px 0 0; color: #b0bec5; font-size: 13px; text-transform: uppercase; letter-spacing: 1px;">All Monitored Dashboards</p>
                        </td>
                    </tr>

                    <!-- Intro Text -->
                    <tr>
                        <td style="padding: 40px 30px 20px 30px;">
                            <p style="font-size: 15px; color: #2d3436; line-height: 1.6; margin: 0;">
                                Here is your weekly summary of mining operations across all monitored sites.
                            </p>
                        </td>
                    </tr>

                    <!-- Dashboard Table -->
                    <tr>
                        <td style="padding: 0 30px 40px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-size: 14px; color: #2d3436; border: 1px solid #e0e0e0;">
                                <tr style="background-color: #fafafa;">
                                    <th align="left" style="padding: 12px 15px; border-bottom: 2px solid #e0e0e0; font-weight: 600;">Dashboard</th>
                                    <th align="center" style="padding: 12px 15px; border-bottom: 2px solid #e0e0e0; font-weight: 600;">Workers</th>
                                    <th align="center" style="padding: 12px 15px; border-bottom: 2px solid #e0e0e0; font-weight: 600;">7-Day</th>
                                    <th align="center" style="padding: 12px 15px; border-bottom: 2px solid #e0e0e0; font-weight: 600;">30-Day</th>
                                    <th align="center" style="padding: 12px 15px; border-bottom: 2px solid #e0e0e0; font-weight: 600;">Status</th>
                                </tr>
                                {table_rows}
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px; background-color: #fafafa; border-top: 1px solid #e0e0e0; font-size: 12px; color: #95a5a6; text-align: center;">
                            Report generated by Code Gray Mining automation.<br/>
                            {current_time.strftime('%B %d, %Y at %I:%M %p')}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    if send_email(subject, body):
        state['last_weekly_report'] = current_time.isoformat()
        print("Weekly report sent successfully")
        return True
    return False


# =============================================================================
# WEB SCRAPING
# =============================================================================

def get_worker_count(dashboard_url):
    """
    Scrape the current worker count from a Luxor watcher dashboard.

    Args:
        dashboard_url: The Luxor watcher URL to scrape

    Returns:
        int: The current worker count, or None if scraping failed
    """
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--incognito')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(dashboard_url)

        wait = WebDriverWait(driver, 20)
        time.sleep(5)

        # Method 1: Find "Active Miners" label and extract count from parent
        try:
            active_miners_element = driver.find_element(
                By.XPATH, "//*[contains(text(), 'Active Miners')]")
            parent = active_miners_element.find_element(By.XPATH, "..")
            count_text = parent.text.replace("Active Miners", "").strip()
            worker_count = int(count_text)
            print(f"Successfully scraped worker count (Method 1): {worker_count}")
            return worker_count
        except Exception as e1:
            print(f"Method 1 failed: {e1}")

        # Method 2: Regex search through all page text
        try:
            import re
            body_text = driver.find_element(By.TAG_NAME, 'body').text
            match = re.search(r'Active Miners\s+(\d+)', body_text)
            if match:
                worker_count = int(match.group(1))
                print(f"Successfully scraped worker count (Method 2): {worker_count}")
                return worker_count
        except Exception as e2:
            print(f"Method 2 failed: {e2}")

        # Method 3: Find green checkmark icon and get adjacent count
        try:
            count_element = driver.find_element(
                By.XPATH, "//svg[contains(@class, 'text-green')]/../following-sibling::*[1]")
            count_text = count_element.text.strip()
            worker_count = int(count_text)
            print(f"Successfully scraped worker count (Method 3): {worker_count}")
            return worker_count
        except Exception as e3:
            print(f"Method 3 failed: {e3}")

        raise Exception("All scraping methods failed")

    except Exception as e:
        print(f"Error scraping page: {e}")
        try:
            if driver:
                all_text = driver.find_element(By.TAG_NAME, 'body').text
                print(f"Debug - Page text sample: {all_text[:500]}")
        except:
            pass
        return None
    finally:
        if driver:
            driver.quit()


# =============================================================================
# SINGLE DASHBOARD CHECK
# =============================================================================

def check_dashboard(miner_config, state, current_time):
    """
    Check a single dashboard and send alerts if needed.

    Args:
        miner_config: Dict with dashboard configuration (name, url, expected_workers, etc.)
        state: Full state dict (will be modified)
        current_time: Current datetime

    Returns:
        bool: True if check succeeded, False if scraping failed
    """
    name = miner_config['name']
    dashboard_url = miner_config['dashboard_url']
    expected_workers = miner_config['expected_workers']
    client_id = miner_config.get('client_id', '')
    machine_types = miner_config.get('machine_types', '')

    print(f"\n--- Checking: {name} ---")
    print(f"Expected workers: {expected_workers}")

    dashboard_state = get_dashboard_state(state, name)

    # Clean old history
    clean_old_history(dashboard_state, current_time)

    # Scrape worker count
    worker_count = get_worker_count(dashboard_url)

    if worker_count is None:
        print(f"ERROR: Could not retrieve worker count for {name}")
        return False

    print(f"Current worker count: {worker_count}")
    print(f"Previous count: {dashboard_state['last_worker_count']}")
    print(f"Last status: {dashboard_state['last_status']}")

    # Determine current status
    if worker_count < expected_workers:
        current_status = 'down'
    else:
        current_status = 'ok'

    # Record in history
    add_history_entry(dashboard_state, current_time, worker_count, current_status)

    # Handle DOWN status
    if worker_count < expected_workers:
        miners_down = expected_workers - worker_count

        if dashboard_state['down_since'] is None:
            dashboard_state['down_since'] = current_time.isoformat()
            print(f"Miners down detected. Started tracking at {current_time}")

        down_since_dt = datetime.fromisoformat(dashboard_state['down_since'])
        down_duration = current_time - down_since_dt
        hours_down = down_duration.total_seconds() / 3600

        print(f"Miners have been down for {hours_down:.1f} hours")

        if hours_down > DOWN_ALERT_THRESHOLD_HOURS:
            should_alert = False
            if dashboard_state['last_alert_time']:
                last_alert = datetime.fromisoformat(dashboard_state['last_alert_time'])
                time_since_alert = current_time - last_alert
                if time_since_alert > timedelta(hours=24):
                    should_alert = True
                    print(f"Re-alerting after {time_since_alert.total_seconds()/3600:.1f} hours")
            else:
                should_alert = True
                print(f"Sending first alert - miners down for {hours_down:.1f} hours")

            if should_alert:
                duration_str = format_duration(hours_down)
                subject = f"ALERT: [{name}] {miners_down} MINER{'S' if miners_down > 1 else ''} DOWN FOR {duration_str.upper()}"
                body = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="margin: 0; padding: 0; background-color: #f8f9fa; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8f9fa; padding: 40px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #e0e0e0; border-collapse: collapse;">
                    <!-- Header with Client Name -->
                    <tr>
                        <td align="left" style="background-color: #1a2b3c; padding: 35px 30px;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 500; letter-spacing: 0.5px;">Miner Status Alert</h1>
                            <p style="margin: 8px 0 0; color: #f39c12; font-size: 16px; font-weight: bold;">{name}</p>
                        </td>
                    </tr>

                    <!-- Intro Text -->
                    <tr>
                        <td style="padding: 40px 30px 20px 30px;">
                            <p style="font-size: 15px; color: #2d3436; line-height: 1.6; margin: 0;">
                                This is an automated notification regarding mining hardware at <strong>{name}</strong>. Our system has detected that several units are currently inactive.
                            </p>
                        </td>
                    </tr>

                    <!-- Stats Cards -->
                    <tr>
                        <td style="padding: 0 30px 30px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse;">
                                <tr>
                                    <td width="33%" align="center" style="padding: 20px; background-color: #fafafa; border: 1px solid #e0e0e0;">
                                        <span style="display: block; font-size: 11px; color: #7f8c8d; text-transform: uppercase; margin-bottom: 5px;">Expected</span>
                                        <span style="font-size: 24px; font-weight: bold; color: #1a2b3c;">{expected_workers}</span>
                                    </td>
                                    <td width="33%" align="center" style="padding: 20px; background-color: #fafafa; border: 1px solid #e0e0e0; border-left: none; border-right: none;">
                                        <span style="display: block; font-size: 11px; color: #7f8c8d; text-transform: uppercase; margin-bottom: 5px;">Online</span>
                                        <span style="font-size: 24px; font-weight: bold; color: #1a2b3c;">{worker_count}</span>
                                    </td>
                                    <td width="33%" align="center" style="padding: 20px; background-color: #fafafa; border: 1px solid #e0e0e0;">
                                        <span style="display: block; font-size: 11px; color: #7f8c8d; text-transform: uppercase; margin-bottom: 5px;">Offline</span>
                                        <span style="font-size: 24px; font-weight: bold; color: #d4a017;">{miners_down}</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Details -->
                    <tr>
                        <td style="padding: 0 30px 40px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-size: 14px; color: #636e72;">
                                <tr>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;"><strong>Site:</strong></td>
                                    <td align="right" style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;">{name}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;"><strong>Down Since:</strong></td>
                                    <td align="right" style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;">{down_since_dt.strftime('%B %d, %Y at %I:%M %p')}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;"><strong>Duration:</strong></td>
                                    <td align="right" style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;">{duration_str}</td>
                                </tr>
                                {f'<tr><td style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;"><strong>Client ID:</strong></td><td align="right" style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;">{client_id}</td></tr>' if client_id else ''}
                                {f'<tr><td style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;"><strong>Machine Types:</strong></td><td align="right" style="padding: 10px 0; border-bottom: 1px solid #f1f1f1;">{machine_types}</td></tr>' if machine_types else ''}
                            </table>
                        </td>
                    </tr>

                    <!-- Buttons -->
                    <tr>
                        <td align="center" style="padding-bottom: 50px;">
                            <table border="0" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center" bgcolor="#1a2b3c" style="border-radius: 4px;">
                                        <a href="{dashboard_url}" style="padding: 12px 25px; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: bold; display: inline-block;">View Dashboard</a>
                                    </td>
                                    <td width="15"></td>
                                    <td align="center" bgcolor="#ffffff" style="border-radius: 4px; border: 1px solid #e0e0e0;">
                                        <a href="{SUPPORT_TICKET_URL}" style="padding: 12px 25px; color: #1a2b3c; text-decoration: none; font-size: 14px; font-weight: bold; display: inline-block;">Open Support Ticket</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px; background-color: #fafafa; border-top: 1px solid #e0e0e0; font-size: 12px; color: #95a5a6; text-align: center;">
                            Alert generated by Code Gray Mining automation.<br/>
                            {current_time.strftime('%B %d, %Y at %I:%M %p')}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
                if send_email(subject, body):
                    dashboard_state['last_alert_time'] = current_time.isoformat()
            else:
                print("Alert suppressed - already notified recently")
        else:
            print(f"Not alerting yet - waiting for {DOWN_ALERT_THRESHOLD_HOURS - hours_down:.1f} more hours")

        dashboard_state['last_status'] = 'down'

    # Handle OK status
    elif worker_count >= expected_workers:
        if dashboard_state['last_status'] == 'down' and dashboard_state['down_since'] is not None:
            down_since_dt = datetime.fromisoformat(dashboard_state['down_since'])
            down_duration = current_time - down_since_dt
            hours_down = down_duration.total_seconds() / 3600

            if hours_down > DOWN_ALERT_THRESHOLD_HOURS:
                duration_str = format_duration(hours_down)
                subject = f"RECOVERY: [{name}] All Miners Back Online"
                body = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="margin: 0; padding: 0; background-color: #f8f9fa; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8f9fa; padding: 40px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #e0e0e0; border-collapse: collapse;">
                    <!-- Header with Client Name -->
                    <tr>
                        <td align="left" style="background-color: #1a2b3c; padding: 35px 30px;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 500; letter-spacing: 0.5px;">All Miners Back Online</h1>
                            <p style="margin: 8px 0 0; color: #27ae60; font-size: 16px; font-weight: bold;">{name}</p>
                        </td>
                    </tr>

                    <!-- Intro Text -->
                    <tr>
                        <td style="padding: 40px 30px 20px 30px;">
                            <p style="font-size: 15px; color: #2d3436; line-height: 1.6; margin: 0;">
                                Good news - all mining units at <strong>{name}</strong> have reconnected and are operating normally.
                            </p>
                        </td>
                    </tr>

                    <!-- Stats Cards -->
                    <tr>
                        <td style="padding: 0 30px 30px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse;">
                                <tr>
                                    <td width="50%" align="center" style="padding: 20px; background-color: #fafafa; border: 1px solid #e0e0e0;">
                                        <span style="display: block; font-size: 11px; color: #7f8c8d; text-transform: uppercase; margin-bottom: 5px;">Miners Online</span>
                                        <span style="font-size: 24px; font-weight: bold; color: #27ae60;">{worker_count}</span>
                                    </td>
                                    <td width="50%" align="center" style="padding: 20px; background-color: #fafafa; border: 1px solid #e0e0e0; border-left: none;">
                                        <span style="display: block; font-size: 11px; color: #7f8c8d; text-transform: uppercase; margin-bottom: 5px;">Total Downtime</span>
                                        <span style="font-size: 24px; font-weight: bold; color: #1a2b3c;">{duration_str}</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Button -->
                    <tr>
                        <td align="center" style="padding-bottom: 50px;">
                            <table border="0" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center" bgcolor="#1a2b3c" style="border-radius: 4px;">
                                        <a href="{dashboard_url}" style="padding: 12px 25px; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: bold; display: inline-block;">View Dashboard</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px; background-color: #fafafa; border-top: 1px solid #e0e0e0; font-size: 12px; color: #95a5a6; text-align: center;">
                            Recovery confirmed by Code Gray Mining automation.<br/>
                            {current_time.strftime('%B %d, %Y at %I:%M %p')}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
                send_email(subject, body)
            else:
                print(f"Miners recovered after {hours_down:.1f} hours (below {DOWN_ALERT_THRESHOLD_HOURS}h threshold, no notification)")

            dashboard_state['down_since'] = None

        dashboard_state['last_status'] = 'ok'
        print(f"Status: OK - All miners online for {name}")

        if worker_count > expected_workers:
            print(f"INFO: Worker count ({worker_count}) exceeds expected ({expected_workers})")

    # Update last worker count
    dashboard_state['last_worker_count'] = worker_count

    return True


# =============================================================================
# MAIN MONITORING LOGIC
# =============================================================================

def check_all_dashboards():
    """
    Main monitoring function - loops through all configured dashboards.

    Continues checking remaining dashboards even if one fails.
    """
    # Load configuration
    try:
        miners_config = load_config()
        print(f"Loaded {len(miners_config)} dashboard(s) from config")
    except (FileNotFoundError, ValueError) as e:
        print(f"CONFIG ERROR: {e}")
        return

    state = load_state()
    current_time = datetime.now()

    print(f"\n{'='*60}")
    print(f"Multi-Dashboard Check started at: {current_time}")
    print(f"{'='*60}")

    # Check each dashboard
    success_count = 0
    fail_count = 0

    for miner_config in miners_config:
        try:
            if check_dashboard(miner_config, state, current_time):
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"ERROR checking {miner_config['name']}: {e}")
            fail_count += 1

    print(f"\n--- Summary: {success_count} succeeded, {fail_count} failed ---")

    # Check if it's time for weekly report
    if state.get('last_weekly_report'):
        last_report = datetime.fromisoformat(state['last_weekly_report'])
        days_since_report = (current_time - last_report).days
        print(f"Days since last weekly report: {days_since_report}")

        if days_since_report >= WEEKLY_REPORT_DAYS:
            print("Sending weekly report...")
            send_weekly_report(state, miners_config)
    else:
        print("Sending first weekly report...")
        send_weekly_report(state, miners_config)

    # Save state
    save_state(state)

    print(f"{'='*60}\n")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    lock_file = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("Another instance is already running. Exiting.")
        sys.exit(0)

    try:
        check_all_dashboards()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        try:
            error_body = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="margin: 0; padding: 0; background-color: #f8f9fa; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8f9fa; padding: 40px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #e0e0e0; border-collapse: collapse;">
                    <!-- Header -->
                    <tr>
                        <td align="left" style="background-color: #1a2b3c; padding: 35px 30px;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 500; letter-spacing: 0.5px;">Script Error</h1>
                            <p style="margin: 8px 0 0; color: #b0bec5; font-size: 13px; text-transform: uppercase; letter-spacing: 1px;">Monitoring Interrupted</p>
                        </td>
                    </tr>

                    <!-- Intro Text -->
                    <tr>
                        <td style="padding: 40px 30px 20px 30px;">
                            <p style="font-size: 15px; color: #2d3436; line-height: 1.6; margin: 0;">
                                The miner monitoring script encountered an error and may need attention.
                            </p>
                        </td>
                    </tr>

                    <!-- Error Details -->
                    <tr>
                        <td style="padding: 0 30px 30px 30px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 20px; background-color: #fafafa; border: 1px solid #e0e0e0;">
                                        <span style="display: block; font-size: 11px; color: #7f8c8d; text-transform: uppercase; margin-bottom: 10px;">Error Details</span>
                                        <span style="font-size: 14px; color: #c0392b; font-family: monospace; word-break: break-word;">{str(e)}</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px; background-color: #fafafa; border-top: 1px solid #e0e0e0; font-size: 12px; color: #95a5a6; text-align: center;">
                            Error logged by Code Gray Mining automation.<br/>
                            {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
            send_email("Monitor Script Error", error_body)
        except:
            pass
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
