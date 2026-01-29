#!/usr/bin/env python3
"""
Luxor Mining Worker Monitor

This script monitors Bitcoin mining workers via the Luxor mining pool dashboard.
It runs hourly (via cron) to check if all expected miners are online, and sends
email alerts when miners go down for extended periods.

Key Features:
- Scrapes worker count from Luxor's web dashboard using Selenium
- Tracks downtime and only alerts after configurable threshold (default: 6 hours)
- Sends recovery notifications when miners come back online
- Generates weekly uptime reports with 7-day and 30-day statistics
- Maintains state between runs for accurate downtime tracking

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

# Luxor watcher URL - Get this from Luxor dashboard > Watcher > Share link
# This is a read-only public link, no login required
TARGET_URL = "https://app.luxor.tech/en/views/watcher?token=watcher-16ba5303d90aa1717695e57800f64fa8"

# Number of miners you expect to be online - alerts trigger when count falls below this
EXPECTED_WORKERS = 57

# Email settings - Uses Gmail SMTP with an "App Password" (not your regular password)
# To create an App Password: Google Account > Security > 2-Step Verification > App Passwords
EMAIL_FROM = "codegraymining@gmail.com"  # Gmail address to send from
EMAIL_TO = "cstott@gmail.com"            # Recipient for alerts
GMAIL_APP_PASSWORD = "oqal afxf qjth purb"  # Gmail App Password (16 chars, spaces ok)

# State and lock files - stored in same directory as script
# STATE_FILE: Persists data between runs (downtime tracking, history, last alert time)
# LOCK_FILE: Prevents multiple instances from running simultaneously
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miner_monitor_state.json")
LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miner_monitor.lock")

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

# Alert timing settings
DOWN_ALERT_THRESHOLD_HOURS = 6  # Only alert after miner is down for this many hours
                                 # (avoids alerts for brief reboots/network blips)
WEEKLY_REPORT_DAYS = 7          # Send uptime report every N days
HISTORY_RETENTION_DAYS = 30     # Keep N days of history for uptime calculations

# Support ticket configuration - for including in alert emails
CLIENT_ID = "mscathy"                      # Your Luxor client ID (for support reference)
MACHINE_TYPES = "M60S+ 202T"               # Your machine types (for support reference)
SUPPORT_EMAIL = "Support@miningstore.com"  # Mining store support email

# Jira Service Desk URL - Direct link to create a support ticket
# Update this URL if your Jira portal changes
SUPPORT_TICKET_URL = "https://miningstore.atlassian.net/servicedesk/customer/portal/1/group/4/create/18"


# =============================================================================
# STATE MANAGEMENT
# =============================================================================
# The state file (miner_monitor_state.json) persists data between script runs.
# This allows the script to track:
#   - When a downtime period started (for the 6-hour threshold)
#   - When the last alert was sent (to avoid spam, re-alerts every 24h)
#   - Historical data for uptime percentage calculations
#
# State file structure (JSON):
# {
#   "last_alert_time": "2024-01-15T10:30:00",  # ISO timestamp of last alert sent
#   "last_worker_count": 57,                   # Worker count from previous check
#   "last_status": "ok",                       # "ok", "down", or "unknown"
#   "down_since": "2024-01-15T04:00:00",       # When current downtime started (null if ok)
#   "last_weekly_report": "2024-01-08T12:00:00", # When last weekly report was sent
#   "history": [                               # Array of historical checks
#     {"timestamp": "...", "worker_count": 57, "status": "ok"},
#     ...
#   ]
# }

def load_state():
    """
    Load previous monitoring state from the JSON state file.

    Returns a dictionary with all state fields. If the file doesn't exist
    (first run) or is missing fields (after an upgrade), default values
    are provided for backward compatibility.
    """
    default_state = {
        'last_alert_time': None,        # When we last sent a down alert
        'last_worker_count': None,      # Worker count from previous check
        'last_status': 'unknown',       # 'ok', 'down', or 'unknown'
        'down_since': None,             # ISO timestamp when current down period started
        'last_weekly_report': None,     # When we last sent weekly report
        'history': []                   # List of {timestamp, worker_count, status} dicts
    }

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            # Add missing keys for backward compatibility
            # (allows adding new fields without breaking existing state files)
            for key, value in default_state.items():
                if key not in state:
                    state[key] = value
            return state

    return default_state


def save_state(state):
    """
    Save monitoring state to the JSON state file.

    Called at the end of each monitoring check to persist:
    - Current status and worker count
    - Downtime tracking info
    - Alert timing info
    - Historical data for uptime reports
    """
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


def send_email(subject, body):
    """Send email via Gmail SMTP"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html'))

        # Connect to Gmail SMTP server
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


def clean_old_history(state, current_time):
    """Remove history entries older than HISTORY_RETENTION_DAYS"""
    cutoff_time = current_time - timedelta(days=HISTORY_RETENTION_DAYS)
    state['history'] = [
        entry for entry in state['history']
        if datetime.fromisoformat(entry['timestamp']) > cutoff_time
    ]


def add_history_entry(state, timestamp, worker_count, status):
    """Add a new history entry"""
    state['history'].append({
        'timestamp': timestamp.isoformat(),
        'worker_count': worker_count,
        'status': status
    })


# =============================================================================
# UPTIME CALCULATION
# =============================================================================

def calculate_uptime_percentage(state, days):
    """
    Calculate uptime percentage for the last N days.

    Uptime is calculated as:
        (checks where worker_count >= EXPECTED_WORKERS) / (total checks) * 100

    For example, if the script runs hourly and 23 out of 24 checks in a day
    showed all miners online, uptime would be 23/24 = 95.8%.

    Note: Uses current EXPECTED_WORKERS value, not the status stored at check time.
    This means if you change EXPECTED_WORKERS, historical uptime will be
    recalculated against the new threshold.

    Args:
        state: The state dictionary containing 'history' list
        days: Number of days to calculate uptime for (e.g., 7 or 30)

    Returns:
        Float percentage (0-100) or None if insufficient data
    """
    if not state['history']:
        return None

    current_time = datetime.now()
    cutoff_time = current_time - timedelta(days=days)

    # Filter history entries to only include the requested time period
    relevant_history = [
        entry for entry in state['history']
        if datetime.fromisoformat(entry['timestamp']) > cutoff_time
    ]

    if not relevant_history:
        return None

    # Count checks where all expected workers were online
    # Compare against current EXPECTED_WORKERS (not stored status) so that
    # changing the expected count recalculates historical uptime correctly
    up_count = sum(1 for entry in relevant_history
                   if entry['worker_count'] >= EXPECTED_WORKERS)
    total_count = len(relevant_history)

    if total_count == 0:
        return None

    return (up_count / total_count) * 100


# =============================================================================
# WEEKLY REPORTS
# =============================================================================

def send_weekly_report(state):
    """
    Send weekly uptime report via email.

    The report includes:
    - 7-day uptime percentage (based on hourly checks)
    - 30-day uptime percentage (for longer-term trends)
    - Current status and worker count

    Reports are sent every WEEKLY_REPORT_DAYS days. The first report is sent
    immediately on the first run. Timing is tracked in state['last_weekly_report'].

    This helps track mining operation health over time and identify patterns
    (e.g., recurring issues at certain times).
    """
    uptime_7d = calculate_uptime_percentage(state, 7)
    uptime_30d = calculate_uptime_percentage(state, 30)

    # Format uptime values - show "Not enough data" until we have history
    if uptime_7d is not None:
        uptime_7d_str = f"{uptime_7d:.1f}%"
    else:
        uptime_7d_str = "Not enough data yet"

    if uptime_30d is not None:
        uptime_30d_str = f"{uptime_30d:.1f}%"
    else:
        uptime_30d_str = "Not enough data yet"

    subject = "Weekly Miner Uptime Report"

    # Determine status color and text
    status_color = "#22c55e" if state['last_status'] == 'ok' else "#ef4444"
    status_text = "All Miners Online" if state['last_status'] == 'ok' else "Miners Offline"

    body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 20px 0;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%;">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); padding: 30px 40px; border-radius: 12px 12px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">Weekly Uptime Report</h1>
                            <p style="margin: 8px 0 0 0; color: #93c5fd; font-size: 14px;">Mining Operations Summary</p>
                        </td>
                    </tr>

                    <!-- Main Content -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 30px 40px;">
                            <!-- Uptime Stats Cards -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td width="48%" style="background-color: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 20px; text-align: center;">
                                        <p style="margin: 0 0 8px 0; color: #0369a1; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">7-Day Uptime</p>
                                        <p style="margin: 0; color: #0c4a6e; font-size: 28px; font-weight: 700;">{uptime_7d_str}</p>
                                    </td>
                                    <td width="4%"></td>
                                    <td width="48%" style="background-color: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 20px; text-align: center;">
                                        <p style="margin: 0 0 8px 0; color: #0369a1; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">30-Day Uptime</p>
                                        <p style="margin: 0; color: #0c4a6e; font-size: 28px; font-weight: 700;">{uptime_30d_str}</p>
                                    </td>
                                </tr>
                            </table>

                            <!-- Current Status -->
                            <div style="margin-top: 25px; padding: 20px; background-color: #fafafa; border-radius: 8px; border-left: 4px solid {status_color};">
                                <h3 style="margin: 0 0 15px 0; color: #374151; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">Current Status</h3>
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Status</td>
                                        <td style="padding: 8px 0; color: {status_color}; font-size: 14px; font-weight: 600; text-align: right;">{status_text}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px;">Expected Workers</td>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #111827; font-size: 14px; font-weight: 500; text-align: right;">{EXPECTED_WORKERS}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px;">Last Count</td>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #111827; font-size: 14px; font-weight: 500; text-align: right;">{state['last_worker_count']}</td>
                                    </tr>
                                </table>
                            </div>

                            <!-- Action Button -->
                            <div style="margin-top: 25px; text-align: center;">
                                <a href="{TARGET_URL}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 30px; border-radius: 6px; font-weight: 500; font-size: 14px;">View Dashboard</a>
                            </div>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 20px 40px; border-radius: 0 0 12px 12px; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #9ca3af; font-size: 12px; text-align: center;">
                                Report generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    if send_email(subject, body):
        state['last_weekly_report'] = datetime.now().isoformat()
        print("Weekly report sent successfully")
        return True
    return False


# =============================================================================
# WEB SCRAPING
# =============================================================================
# The script uses Selenium to scrape the worker count from Luxor's dashboard.
# We use 3 different methods as fallbacks because:
#   1. Luxor may update their UI/HTML structure at any time
#   2. Different UI versions may be served (A/B testing)
#   3. Page load timing can affect element availability
#
# If all methods fail, check the Luxor dashboard manually and update the
# XPath selectors below to match the current HTML structure.

def get_worker_count():
    """
    Scrape the current worker count from the Luxor watcher dashboard.

    Uses headless Chrome (via Selenium) to load the page and extract the
    "Active Miners" count. Three different scraping methods are attempted
    as fallbacks in case Luxor changes their UI.

    Returns:
        int: The current worker count, or None if scraping failed

    Requirements:
        - Chrome/Chromium browser installed
        - ChromeDriver installed and in PATH
        - On Linux servers: may need additional packages for headless Chrome
    """
    # Configure Chrome to run headless (no visible browser window)
    options = Options()
    options.add_argument('--headless')                # Run without GUI
    options.add_argument('--no-sandbox')              # Required for running as root
    options.add_argument('--disable-dev-shm-usage')   # Overcome limited /dev/shm in Docker
    options.add_argument('--incognito')               # Don't use cached data
    options.add_argument('--disable-blink-features=AutomationControlled')  # Avoid bot detection
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(TARGET_URL)

        # Wait for the page to load - Luxor uses React so content loads dynamically
        wait = WebDriverWait(driver, 20)
        time.sleep(5)  # Extra time for JavaScript to populate data

        # =====================================================================
        # Method 1: Find "Active Miners" label and extract count from parent
        # =====================================================================
        # Looks for text "Active Miners" and gets the number from the same container
        # Works when the label and count are in a parent-child relationship
        try:
            active_miners_element = driver.find_element(
                By.XPATH, "//*[contains(text(), 'Active Miners')]")
            # Navigate to parent element which contains both label and count
            parent = active_miners_element.find_element(By.XPATH, "..")
            count_text = parent.text.replace("Active Miners", "").strip()
            worker_count = int(count_text)
            print(
                f"Successfully scraped worker count (Method 1): {worker_count}")
            return worker_count
        except Exception as e1:
            print(f"Method 1 failed: {e1}")

        # =====================================================================
        # Method 2: Regex search through all page text
        # =====================================================================
        # More robust - searches the entire page text for "Active Miners" followed
        # by a number. Works even if HTML structure changes, as long as the text
        # pattern remains the same.
        try:
            import re
            body_text = driver.find_element(By.TAG_NAME, 'body').text
            match = re.search(r'Active Miners\s+(\d+)', body_text)
            if match:
                worker_count = int(match.group(1))
                print(
                    f"Successfully scraped worker count (Method 2): {worker_count}")
                return worker_count
        except Exception as e2:
            print(f"Method 2 failed: {e2}")

        # =====================================================================
        # Method 3: Find green checkmark icon and get adjacent count
        # =====================================================================
        # Looks for the green status icon (SVG with text-green class) which
        # indicates active workers, then finds the number next to it.
        # Based on original dashboard screenshot analysis.
        try:
            count_element = driver.find_element(
                By.XPATH, "//svg[contains(@class, 'text-green')]/../following-sibling::*[1]")
            count_text = count_element.text.strip()
            worker_count = int(count_text)
            print(
                f"Successfully scraped worker count (Method 3): {worker_count}")
            return worker_count
        except Exception as e3:
            print(f"Method 3 failed: {e3}")

        raise Exception("All scraping methods failed")

    except Exception as e:
        print(f"Error scraping page: {e}")

        # Debug output - print page text to help diagnose scraping failures
        try:
            if driver:
                all_text = driver.find_element(By.TAG_NAME, 'body').text
                print(f"Debug - Page text sample: {all_text[:500]}")
        except:
            pass

        return None
    finally:
        # Always close the browser to free resources
        if driver:
            driver.quit()


# =============================================================================
# MAIN MONITORING LOGIC
# =============================================================================

def check_and_alert():
    """
    Main monitoring function - called once per script execution (typically hourly).

    This function orchestrates the entire monitoring workflow:
    1. Load previous state from file
    2. Scrape current worker count from Luxor
    3. Compare against expected count
    4. Track downtime duration if miners are down
    5. Send alert if downtime exceeds threshold (default: 6 hours)
    6. Send recovery notification when miners come back online
    7. Send weekly uptime report if due
    8. Save updated state for next run

    Alert Logic:
    - First alert: Sent after DOWN_ALERT_THRESHOLD_HOURS (6h) of continuous downtime
    - Re-alerts: Every 24 hours while miners remain down
    - Recovery: Sent when miners come back online (only if we sent a down alert)

    This approach avoids alert spam from brief outages (reboots, network blips)
    while ensuring extended outages are noticed and tracked.
    """
    state = load_state()
    current_time = datetime.now()

    print(f"\n{'='*50}")
    print(f"Check started at: {current_time}")
    print(f"{'='*50}")

    # Remove history entries older than HISTORY_RETENTION_DAYS to prevent
    # unbounded growth of the state file
    clean_old_history(state, current_time)

    # Scrape current worker count from Luxor dashboard
    worker_count = get_worker_count()

    if worker_count is None:
        # Scraping failed - could be network issue, Luxor down, or UI change
        # Don't update state to avoid corrupting downtime tracking
        print("ERROR: Could not retrieve worker count")
        return

    print(f"Current worker count: {worker_count}")
    print(f"Expected worker count: {EXPECTED_WORKERS}")
    print(f"Previous count: {state['last_worker_count']}")
    print(f"Last status: {state['last_status']}")

    # Determine current status based on worker count
    if worker_count < EXPECTED_WORKERS:
        current_status = 'down'
    else:
        current_status = 'ok'

    # Record this check in history for uptime calculations
    add_history_entry(state, current_time, worker_count, current_status)

    # =========================================================================
    # Handle DOWN status - one or more miners offline
    # =========================================================================
    if worker_count < EXPECTED_WORKERS:
        miners_down = EXPECTED_WORKERS - worker_count

        # Start tracking downtime if this is first detection
        if state['down_since'] is None:
            state['down_since'] = current_time.isoformat()
            print(f"Miners down detected. Started tracking at {current_time}")

        # Calculate total downtime duration
        down_since_dt = datetime.fromisoformat(state['down_since'])
        down_duration = current_time - down_since_dt
        hours_down = down_duration.total_seconds() / 3600

        print(f"Miners have been down for {hours_down:.1f} hours")

        # Only alert if down for more than the threshold (default: 6 hours)
        # This avoids alerts for brief reboots or network blips
        if hours_down > DOWN_ALERT_THRESHOLD_HOURS:
            # Determine if we should send an alert
            should_alert = False
            if state['last_alert_time']:
                last_alert = datetime.fromisoformat(state['last_alert_time'])
                time_since_alert = current_time - last_alert
                # Re-alert every 24 hours to remind about ongoing issues
                if time_since_alert > timedelta(hours=24):
                    should_alert = True
                    print(f"Re-alerting after {time_since_alert.total_seconds()/3600:.1f} hours")
            else:
                # No previous alert - this is the first one for this outage
                should_alert = True
                print(f"Sending first alert - miners down for {hours_down:.1f} hours")

            if should_alert:
                duration_str = format_duration(hours_down)
                subject = f"ALERT: {miners_down} MINER DOWN FOR {duration_str.upper()}"
                body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 20px 0;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%;">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #991b1b 0%, #dc2626 100%); padding: 30px 40px; border-radius: 12px 12px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">Miner Alert</h1>
                            <p style="margin: 8px 0 0 0; color: #fecaca; font-size: 14px;">Immediate attention required</p>
                        </td>
                    </tr>

                    <!-- Alert Banner -->
                    <tr>
                        <td style="background-color: #fef2f2; padding: 20px 40px; border-bottom: 1px solid #fecaca;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td>
                                        <p style="margin: 0; color: #991b1b; font-size: 32px; font-weight: 700;">{miners_down} Miner{'s' if miners_down > 1 else ''} Down</p>
                                        <p style="margin: 5px 0 0 0; color: #b91c1c; font-size: 16px;">for {duration_str}</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Main Content -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 30px 40px;">
                            <!-- Status Details -->
                            <div style="padding: 20px; background-color: #fafafa; border-radius: 8px; border-left: 4px solid #ef4444;">
                                <h3 style="margin: 0 0 15px 0; color: #374151; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">Status Details</h3>
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Expected Workers</td>
                                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 500; text-align: right;">{EXPECTED_WORKERS}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px;">Current Workers</td>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #ef4444; font-size: 14px; font-weight: 600; text-align: right;">{worker_count}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px;">Miners Offline</td>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #ef4444; font-size: 14px; font-weight: 600; text-align: right;">{miners_down}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px;">Down Since</td>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #111827; font-size: 14px; font-weight: 500; text-align: right;">{down_since_dt.strftime('%b %d, %Y %I:%M %p')}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px;">Duration</td>
                                        <td style="padding: 8px 0; border-top: 1px solid #e5e7eb; color: #111827; font-size: 14px; font-weight: 500; text-align: right;">{duration_str}</td>
                                    </tr>
                                </table>
                            </div>

                            <!-- Action Buttons -->
                            <div style="margin-top: 25px; text-align: center;">
                                <a href="{TARGET_URL}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 500; font-size: 14px; margin-right: 10px;">View Dashboard</a>
                                <a href="{SUPPORT_TICKET_URL}" style="display: inline-block; background-color: #dc2626; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 500; font-size: 14px;">Open Support Ticket</a>
                            </div>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 20px 40px; border-radius: 0 0 12px 12px; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #9ca3af; font-size: 12px; text-align: center;">
                                Alert generated {current_time.strftime('%B %d, %Y at %I:%M %p')}
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
                if send_email(subject, body):
                    state['last_alert_time'] = current_time.isoformat()
            else:
                print("Alert suppressed - already notified recently")
        else:
            print(f"Not alerting yet - waiting for {DOWN_ALERT_THRESHOLD_HOURS - hours_down:.1f} more hours")

        state['last_status'] = 'down'

    # =========================================================================
    # Handle OK status - all miners online
    # =========================================================================
    elif worker_count >= EXPECTED_WORKERS:
        # Check if we're recovering from a down state
        if state['last_status'] == 'down' and state['down_since'] is not None:
            down_since_dt = datetime.fromisoformat(state['down_since'])
            down_duration = current_time - down_since_dt
            hours_down = down_duration.total_seconds() / 3600

            # Only send recovery email if downtime exceeded the alert threshold
            # (no point sending "recovered" if we never sent "down")
            if hours_down > DOWN_ALERT_THRESHOLD_HOURS:
                duration_str = format_duration(hours_down)
                subject = "RECOVERY - All Miners Back Online"
                body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 20px 0;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%;">
                    <!-- Header -->
                    <tr>
                        <td style="background-color: #22c55e; padding: 30px 40px; border-radius: 12px 12px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">All {worker_count} Miners Online</h1>
                            <p style="margin: 8px 0 0 0; color: #bbf7d0; font-size: 14px;">Recovered after {duration_str}</p>
                        </td>
                    </tr>

                    <!-- Main Content -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 30px 40px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="font-size: 14px;">
                                <tr>
                                    <td style="padding: 10px 0; color: #6b7280;">Previous Count</td>
                                    <td style="padding: 10px 0; color: #111827; font-weight: 500; text-align: right;">{state['last_worker_count']} miners</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; border-top: 1px solid #e5e7eb; color: #6b7280;">Total Downtime</td>
                                    <td style="padding: 10px 0; border-top: 1px solid #e5e7eb; color: #111827; font-weight: 500; text-align: right;">{duration_str}</td>
                                </tr>
                            </table>

                            <div style="margin-top: 25px; text-align: center;">
                                <a href="{TARGET_URL}" style="display: inline-block; background-color: #22c55e; color: #ffffff; text-decoration: none; padding: 12px 30px; border-radius: 6px; font-weight: 500; font-size: 14px;">View Dashboard</a>
                            </div>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 15px 40px; border-radius: 0 0 12px 12px; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #9ca3af; font-size: 12px; text-align: center;">{current_time.strftime('%B %d, %Y at %I:%M %p')}</p>
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

            # Clear downtime tracking - reset for next potential outage
            state['down_since'] = None

        state['last_status'] = 'ok'
        print("Status: OK - All miners online")

        # Log if we have more workers than expected (informational only)
        if worker_count > EXPECTED_WORKERS:
            print(f"INFO: Worker count ({worker_count}) exceeds expected ({EXPECTED_WORKERS})")

    # Check if it's time for weekly report
    if state['last_weekly_report']:
        last_report = datetime.fromisoformat(state['last_weekly_report'])
        days_since_report = (current_time - last_report).days
        print(f"Days since last weekly report: {days_since_report}")

        if days_since_report >= WEEKLY_REPORT_DAYS:
            print("Sending weekly report...")
            send_weekly_report(state)
    else:
        # Never sent a report, send the first one
        print("Sending first weekly report...")
        send_weekly_report(state)

    # Update state
    state['last_worker_count'] = worker_count
    save_state(state)

    print(f"{'='*50}\n")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
# This block runs when the script is executed directly (not imported).
# Key features:
#   1. File locking - Prevents multiple instances from running simultaneously
#      (important when cron jobs overlap or take longer than expected)
#   2. Error handling - Sends email notification if script crashes
#   3. Clean resource release - Always releases lock file

if __name__ == "__main__":
    # =========================================================================
    # File Locking
    # =========================================================================
    # Use exclusive file lock to prevent concurrent script executions.
    # This is important because:
    #   - Cron may start a new instance before the previous one finishes
    #   - Multiple instances could corrupt the state file
    #   - Multiple instances could send duplicate alerts
    #
    # LOCK_NB (non-blocking) means we exit immediately if lock is held,
    # rather than waiting indefinitely.
    lock_file = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        # Another instance holds the lock - exit silently
        print("Another instance is already running. Exiting.")
        sys.exit(0)

    try:
        # Run the main monitoring logic
        check_and_alert()
    except Exception as e:
        # =====================================================================
        # Error Notification
        # =====================================================================
        # If anything crashes, try to send an email so the issue is noticed.
        # This catches unexpected errors like:
        #   - ChromeDriver not found
        #   - Network connectivity issues
        #   - State file corruption
        #   - Selenium/Chrome version mismatches
        print(f"FATAL ERROR: {e}")
        try:
            error_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 20px 0;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%;">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #92400e 0%, #f59e0b 100%); padding: 30px 40px; border-radius: 12px 12px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">Script Error</h1>
                            <p style="margin: 8px 0 0 0; color: #fef3c7; font-size: 14px;">Monitoring interrupted</p>
                        </td>
                    </tr>

                    <!-- Warning Banner -->
                    <tr>
                        <td style="background-color: #fffbeb; padding: 20px 40px; border-bottom: 1px solid #fde68a;">
                            <p style="margin: 0; color: #92400e; font-size: 16px; font-weight: 500;">The miner monitoring script encountered an error and may need attention.</p>
                        </td>
                    </tr>

                    <!-- Main Content -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 30px 40px;">
                            <!-- Error Details -->
                            <div style="padding: 20px; background-color: #fef2f2; border-radius: 8px; border-left: 4px solid #ef4444;">
                                <h3 style="margin: 0 0 10px 0; color: #991b1b; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">Error Details</h3>
                                <p style="margin: 0; color: #7f1d1d; font-size: 14px; font-family: monospace; word-break: break-word;">{str(e)}</p>
                            </div>

                            <!-- Troubleshooting -->
                            <div style="margin-top: 25px; padding: 20px; background-color: #fafafa; border-radius: 8px;">
                                <h3 style="margin: 0 0 15px 0; color: #374151; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">Troubleshooting Steps</h3>
                                <ul style="margin: 0; padding-left: 20px; color: #4b5563; font-size: 14px; line-height: 1.8;">
                                    <li>Check monitor.log for detailed error information</li>
                                    <li>Verify ChromeDriver is installed and working</li>
                                    <li>Ensure network connectivity to Luxor dashboard</li>
                                    <li>Try restarting the monitoring script</li>
                                </ul>
                            </div>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 20px 40px; border-radius: 0 0 12px 12px; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #9ca3af; font-size: 12px; text-align: center;">
                                Error occurred {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
                            </p>
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
            # If email fails too, nothing more we can do
            pass
    finally:
        # Always release the lock, even if an error occurred
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
