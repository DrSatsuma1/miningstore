#!/usr/bin/env python3
"""
Luxor Mining Worker Monitor
Checks worker count every hour and alerts when miners go down
"""

import json
import os
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configuration
TARGET_URL = "https://app.luxor.tech/en/views/watcher?token=watcher-16ba5303d90aa1717695e57800f64fa8"
EXPECTED_WORKERS = 57
EMAIL_FROM = "codegraymining@gmail.com"
EMAIL_TO = "cstott@gmail.com"
GMAIL_APP_PASSWORD = "oqal afxf qjth purb"
# Store state file in same directory as script to avoid permission issues
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miner_monitor_state.json")
DOWN_ALERT_THRESHOLD_HOURS = 5  # Only alert after miner is down for 5 hours
WEEKLY_REPORT_DAYS = 7  # Send report every 7 days
HISTORY_RETENTION_DAYS = 30  # Keep 30 days of history

# Support ticket configuration
CLIENT_ID = "mscathy"  # Your Luxor client ID
MACHINE_TYPES = "M60S+ 202T"  # Your machine types
SUPPORT_EMAIL = "Support@miningstore.com"  # Mining store support email


def load_state():
    """Load previous state from file"""
    default_state = {
        'last_alert_time': None,
        'last_worker_count': None,
        'last_status': 'unknown',
        'down_since': None,  # When current down period started
        'last_weekly_report': None,  # When we last sent weekly report
        'history': []  # Historical checks for uptime calculation
    }

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            # Add missing keys for backward compatibility
            for key, value in default_state.items():
                if key not in state:
                    state[key] = value
            return state

    return default_state


def save_state(state):
    """Save state to file"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


def send_email(subject, body):
    """Send email via Gmail SMTP"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

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


def calculate_uptime_percentage(state, days):
    """Calculate uptime percentage for the last N days"""
    if not state['history']:
        return None

    current_time = datetime.now()
    cutoff_time = current_time - timedelta(days=days)

    # Filter history for the time period
    relevant_history = [
        entry for entry in state['history']
        if datetime.fromisoformat(entry['timestamp']) > cutoff_time
    ]

    if not relevant_history:
        return None

    # Calculate uptime (count checks where miners were up)
    up_count = sum(1 for entry in relevant_history if entry['status'] == 'ok')
    total_count = len(relevant_history)

    if total_count == 0:
        return None

    return (up_count / total_count) * 100


def send_weekly_report(state):
    """Send weekly uptime report"""
    uptime_7d = calculate_uptime_percentage(state, 7)
    uptime_30d = calculate_uptime_percentage(state, 30)

    # Format uptime values
    if uptime_7d is not None:
        uptime_7d_str = f"{uptime_7d:.1f}%"
    else:
        uptime_7d_str = "Not enough data yet"

    if uptime_30d is not None:
        uptime_30d_str = f"{uptime_30d:.1f}%"
    else:
        uptime_30d_str = "Not enough data yet"

    subject = "Weekly Miner Uptime Report"
    body = f"""Weekly Miner Uptime Report

Uptime Statistics:
==================
Last 7 days:  {uptime_7d_str}
Last 30 days: {uptime_30d_str}

Current Status:
===============
Expected workers: {EXPECTED_WORKERS}
Last count: {state['last_worker_count']}
Status: {state['last_status']}

Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    if send_email(subject, body):
        state['last_weekly_report'] = datetime.now().isoformat()
        print("Weekly report sent successfully")
        return True
    return False


def get_worker_count():
    """Scrape worker count from Luxor dashboard"""
    options = Options()
    options.add_argument('--headless')  # Run in background
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--incognito')  # Incognito mode
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(TARGET_URL)

        # Wait for the page to load
        wait = WebDriverWait(driver, 20)
        time.sleep(5)  # Give extra time for dynamic content

        # Method 1: Look for "Active Miners" text and get the next element
        try:
            active_miners_element = driver.find_element(
                By.XPATH, "//*[contains(text(), 'Active Miners')]")
            # Get the parent and then find the number
            parent = active_miners_element.find_element(By.XPATH, "..")
            count_text = parent.text.replace("Active Miners", "").strip()
            worker_count = int(count_text)
            print(
                f"Successfully scraped worker count (Method 1): {worker_count}")
            return worker_count
        except Exception as e1:
            print(f"Method 1 failed: {e1}")

        # Method 2: Use regex to find the number after "Active Miners"
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

        # Method 3: Look in the Workers section with green checkmark (original screenshot method)
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

        # Debug output
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


def check_and_alert():
    """Main monitoring logic"""
    state = load_state()
    current_time = datetime.now()

    print(f"\n{'='*50}")
    print(f"Check started at: {current_time}")
    print(f"{'='*50}")

    # Clean old history
    clean_old_history(state, current_time)

    # Get current worker count
    worker_count = get_worker_count()

    if worker_count is None:
        print("ERROR: Could not retrieve worker count")
        return

    print(f"Current worker count: {worker_count}")
    print(f"Expected worker count: {EXPECTED_WORKERS}")
    print(f"Previous count: {state['last_worker_count']}")
    print(f"Last status: {state['last_status']}")

    # Determine current status
    if worker_count < EXPECTED_WORKERS:
        current_status = 'down'
    else:
        current_status = 'ok'

    # Add to history
    add_history_entry(state, current_time, worker_count, current_status)

    # Handle down status
    if worker_count < EXPECTED_WORKERS:
        miners_down = EXPECTED_WORKERS - worker_count

        # Track when the down period started
        if state['down_since'] is None:
            # First time detecting miners down
            state['down_since'] = current_time.isoformat()
            print(f"Miners down detected. Started tracking at {current_time}")

        # Calculate how long miners have been down
        down_since_dt = datetime.fromisoformat(state['down_since'])
        down_duration = current_time - down_since_dt
        hours_down = down_duration.total_seconds() / 3600

        print(f"Miners have been down for {hours_down:.1f} hours")

        # Only alert if down for more than 5 hours
        if hours_down > DOWN_ALERT_THRESHOLD_HOURS:
            # Check if we haven't alerted recently
            should_alert = False
            if state['last_alert_time']:
                last_alert = datetime.fromisoformat(state['last_alert_time'])
                time_since_alert = current_time - last_alert
                # Re-alert every 24 hours after initial 5-hour threshold
                if time_since_alert > timedelta(hours=24):
                    should_alert = True
                    print(f"Re-alerting after {time_since_alert.total_seconds()/3600:.1f} hours")
            else:
                should_alert = True
                print(f"Sending first alert - miners down for {hours_down:.1f} hours")

            if should_alert:
                subject = f"ALERT: {miners_down} MINER DOWN FOR {hours_down:.1f} HOURS"
                body = f"""Miner Alert!

Expected workers: {EXPECTED_WORKERS}
Current workers: {worker_count}
Miners down: {miners_down}
Down since: {down_since_dt.strftime('%Y-%m-%d %H:%M:%S')}
Duration: {hours_down:.1f} hours

Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
URL: {TARGET_URL}
"""
                if send_email(subject, body):
                    state['last_alert_time'] = current_time.isoformat()
            else:
                print("Alert suppressed - already notified recently")
        else:
            print(f"Not alerting yet - waiting for {DOWN_ALERT_THRESHOLD_HOURS - hours_down:.1f} more hours")

        state['last_status'] = 'down'

    elif worker_count >= EXPECTED_WORKERS:
        # All miners are up (or more)
        if state['last_status'] == 'down' and state['down_since'] is not None:
            # Send recovery email
            down_since_dt = datetime.fromisoformat(state['down_since'])
            down_duration = current_time - down_since_dt
            hours_down = down_duration.total_seconds() / 3600

            subject = "RECOVERY - All Miners Back Online"
            body = f"""All miners have recovered!

Expected workers: {EXPECTED_WORKERS}
Current workers: {worker_count}
Previous count: {state['last_worker_count']}
Total downtime: {hours_down:.1f} hours

View Dashboard: {TARGET_URL}


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            send_email(subject, body)

            # Clear down tracking
            state['down_since'] = None

        state['last_status'] = 'ok'
        print("Status: OK - All miners online")

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


if __name__ == "__main__":
    try:
        check_and_alert()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        # Try to send error notification
        try:
            error_body = f"""
MONITORING SCRIPT ERROR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ Script Error

The miner monitoring script encountered an error and may need attention.


ERROR DETAILS

{str(e)}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


TROUBLESHOOTING

  • Check monitor.log for detailed error information
  • Verify ChromeDriver is installed and working
  • Ensure network connectivity to Luxor dashboard
  • Try restarting the monitoring script


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            send_email("⚠️ Monitor Script Error", error_body)
        except:
            pass
