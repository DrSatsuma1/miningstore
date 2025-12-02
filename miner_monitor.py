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
STATE_FILE = "/tmp/miner_monitor_state.json"
ALERT_COOLDOWN_HOURS = 12

# Support ticket configuration
CLIENT_ID = "mscathy"  # Your Luxor client ID
MACHINE_TYPES = "M60S+ 202T"  # Your machine types
SUPPORT_EMAIL = "Support@miningstore.com"  # Mining store support email


def load_state():
    """Load previous state from file"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        'last_alert_time': None,
        'last_worker_count': None,
        'last_status': 'unknown',
        'offline_start_time': None,
        'support_ticket_offered': False
    }


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


def take_luxor_screenshot():
    """Take a screenshot of the Luxor dashboard and return the file path"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--incognito')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_argument('--window-size=1920,1080')  # Full size for screenshot

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(TARGET_URL)

        # Wait for the page to load
        time.sleep(5)

        # Take screenshot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f"/tmp/luxor_dashboard_{timestamp}.png"
        driver.save_screenshot(screenshot_path)

        print(f"Screenshot saved to: {screenshot_path}")
        return screenshot_path

    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def send_support_ticket_email(miners_down, offline_duration_hours):
    """Send email with support ticket creation link and attached screenshot"""
    import urllib.parse
    from email.mime.image import MIMEImage

    # Take a screenshot of the Luxor dashboard
    screenshot_path = take_luxor_screenshot()

    # Prepare the support ticket email content
    ticket_subject = f"Support Request - {miners_down} Miner(s) Offline"
    ticket_body = f"""Hello Mining Store Support Team,

I am experiencing issues with my mining equipment and would like to request support.

Client ID: {CLIENT_ID}

Machine Types: {MACHINE_TYPES}

Issue: {miners_down} miner(s) have been offline for approximately {offline_duration_hours:.1f} hours.

Luxor Dashboard: {TARGET_URL}

I will attach a screenshot of my full Luxor page to help your technicians investigate this issue more swiftly.

Thank you for your assistance.

Best regards"""

    # URL encode the mailto link
    mailto_link = f"mailto:{SUPPORT_EMAIL}?subject={urllib.parse.quote(ticket_subject)}&body={urllib.parse.quote(ticket_body)}"

    # Email to the user asking if they want to create a support ticket
    subject = f"⚠️ Action Required: {miners_down} Miner{'s' if miners_down > 1 else ''} Offline for {offline_duration_hours:.1f}h"
    body = f"""
SUPPORT TICKET AVAILABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 OFFLINE ALERT

Your miners have been offline for {offline_duration_hours:.1f} hours and may need professional
support from Mining Store.


CURRENT STATUS

  Expected Workers     {EXPECTED_WORKERS}
  Offline Miners       {miners_down}
  Offline Duration     {offline_duration_hours:.1f} hours


CREATE SUPPORT TICKET

Click the link below to open a pre-filled support request:

  👉 {mailto_link}

This opens your email client with a draft to {SUPPORT_EMAIL} including:

  • Client ID: {CLIENT_ID}
  • Machine Types: {MACHINE_TYPES}
  • Issue details and offline duration
  • Dashboard link


SCREENSHOT ATTACHED

A full screenshot of your Luxor dashboard is attached to this email.
You'll need to add this to your support request.


HOW TO SUBMIT

  1. Click the mailto link above
  2. Download the attached screenshot (luxor_dashboard_*.png)
  3. Attach screenshot to the support email
  4. Review and edit if needed
  5. Send

Note: The support email will NOT send automatically. You're in control.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
View Dashboard: {TARGET_URL}
"""

    # Send email with screenshot attachment
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        # Attach screenshot if available
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                img_data = f.read()
                image = MIMEImage(img_data, name=os.path.basename(screenshot_path))
                msg.attach(image)
                print(f"Screenshot attached to email: {screenshot_path}")
        else:
            print("Warning: Screenshot not available, sending email without attachment")

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

    # Get current worker count
    worker_count = get_worker_count()

    if worker_count is None:
        print("ERROR: Could not retrieve worker count")
        return

    print(f"Current worker count: {worker_count}")
    print(f"Expected worker count: {EXPECTED_WORKERS}")
    print(f"Previous count: {state['last_worker_count']}")
    print(f"Last status: {state['last_status']}")

    # Determine if we should send alerts
    should_alert = False
    should_send_recovery = False

    if worker_count < EXPECTED_WORKERS:
        # Miners are down
        miners_down = EXPECTED_WORKERS - worker_count

        # Track when miners first went offline
        if not state.get('offline_start_time'):
            state['offline_start_time'] = current_time.isoformat()
            print(f"Miners went offline at: {current_time}")

        # Calculate offline duration
        offline_start = datetime.fromisoformat(state['offline_start_time'])
        offline_duration = current_time - offline_start
        offline_hours = offline_duration.total_seconds() / 3600
        print(f"Offline duration: {offline_hours:.1f} hours")

        # Check if we should alert (not alerted recently)
        if state['last_alert_time']:
            last_alert = datetime.fromisoformat(state['last_alert_time'])
            time_since_alert = current_time - last_alert
            if time_since_alert > timedelta(hours=ALERT_COOLDOWN_HOURS):
                should_alert = True
                print(
                    f"Alert cooldown expired ({time_since_alert.total_seconds()/3600:.1f} hours ago)")
        else:
            should_alert = True
            print("First time detecting issue - will alert")

        if should_alert:
            subject = f"🚨 Alert: {miners_down} Miner{'s' if miners_down > 1 else ''} Offline"
            body = f"""
MINER OFFLINE ALERT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 {miners_down} miner{'s are' if miners_down > 1 else ' is'} currently offline


DETAILS

  Expected Workers     {EXPECTED_WORKERS}
  Current Workers      {worker_count}
  Miners Offline       {miners_down}

  Detected             {current_time.strftime('%Y-%m-%d %H:%M:%S')}


NEXT STEPS

  • Monitor your dashboard for status changes
  • If offline for {ALERT_COOLDOWN_HOURS}+ hours, you'll receive support ticket option

View Dashboard: {TARGET_URL}


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Next alert in {ALERT_COOLDOWN_HOURS} hours (unless status changes)
"""
            if send_email(subject, body):
                state['last_alert_time'] = current_time.isoformat()
                state['last_status'] = 'down'
        else:
            print("Alert suppressed - within cooldown period")
            state['last_status'] = 'down'

        # Check if we should offer support ticket creation
        if offline_hours >= ALERT_COOLDOWN_HOURS and not state.get('support_ticket_offered'):
            print(f"Miners have been offline for {offline_hours:.1f} hours - offering support ticket")
            if send_support_ticket_email(miners_down, offline_hours):
                state['support_ticket_offered'] = True
                print("Support ticket email sent successfully")
            else:
                print("Failed to send support ticket email")

    elif worker_count == EXPECTED_WORKERS:
        # All miners are up
        if state['last_status'] == 'down' or state['last_worker_count'] and state['last_worker_count'] < EXPECTED_WORKERS:
            # Send recovery email
            should_send_recovery = True
            subject = f"✅ Recovery: All Miners Back Online"
            body = f"""
ALL MINERS RECOVERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🟢 All miners are back online!


DETAILS

  Expected Workers     {EXPECTED_WORKERS}
  Current Workers      {worker_count}
  Previous Count       {state['last_worker_count']}

  Recovered            {current_time.strftime('%Y-%m-%d %H:%M:%S')}


Your mining operations have returned to normal.

View Dashboard: {TARGET_URL}


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            send_email(subject, body)

        # Clear offline tracking since miners are back online
        state['offline_start_time'] = None
        state['support_ticket_offered'] = False
        state['last_status'] = 'ok'
        print("Status: OK - All miners online")

    else:
        # More workers than expected (worker_count > EXPECTED_WORKERS)
        print(
            f"INFO: Worker count ({worker_count}) exceeds expected ({EXPECTED_WORKERS})")
        state['last_status'] = 'ok'

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
