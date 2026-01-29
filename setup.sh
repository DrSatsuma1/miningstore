#!/bin/bash
# =============================================================================
#
#                     MINER MONITOR SETUP SCRIPT
#
# This script installs all dependencies needed to run the miner monitor
# on a Linux VPS (Ubuntu/Debian).
#
# What it installs:
#   - Python 3 and pip (package manager)
#   - Google Chrome (headless browser for web scraping)
#   - ChromeDriver (Selenium controller for Chrome)
#   - Selenium Python package
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
#
# =============================================================================

echo "=========================================="
echo "Luxor Miner Monitor - Installation Script"
echo "=========================================="
echo ""

# -----------------------------------------------------------------------------
# Step 1: Update package list
# -----------------------------------------------------------------------------
# This refreshes the list of available packages from Ubuntu/Debian repositories.
# Always do this before installing new packages to get the latest versions.
echo "[1/5] Updating package list..."
sudo apt-get update

# -----------------------------------------------------------------------------
# Step 2: Install Python3 and pip
# -----------------------------------------------------------------------------
# Python3 is the programming language the script is written in.
# pip is the package manager for installing Python libraries.
echo "[2/5] Installing Python3 and pip..."
sudo apt-get install -y python3 python3-pip

# -----------------------------------------------------------------------------
# Step 3: Install Google Chrome
# -----------------------------------------------------------------------------
# Chrome is needed because:
#   - Luxor uses JavaScript to render the dashboard (simple HTTP won't work)
#   - Selenium controls Chrome to load and scrape the page
#   - We use "headless" mode (no visible window) for server environments
echo "[3/5] Installing Google Chrome..."
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
sudo apt-get update
sudo apt-get install -y google-chrome-stable

# -----------------------------------------------------------------------------
# Step 4: Install ChromeDriver
# -----------------------------------------------------------------------------
# ChromeDriver is the bridge between Selenium and Chrome.
# It must match your Chrome version!
#
# This downloads the latest version automatically.
# If you have issues, manually download from: https://chromedriver.chromium.org/downloads
echo "[4/5] Installing ChromeDriver..."
CHROME_DRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE)
wget -N https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip -P /tmp
unzip -o /tmp/chromedriver_linux64.zip -d /tmp
sudo mv /tmp/chromedriver /usr/local/bin/chromedriver
sudo chmod +x /usr/local/bin/chromedriver
rm /tmp/chromedriver_linux64.zip

# -----------------------------------------------------------------------------
# Step 5: Install Python packages
# -----------------------------------------------------------------------------
# Selenium is the Python library that controls web browsers.
echo "[5/5] Installing Python packages..."
pip3 install selenium

# -----------------------------------------------------------------------------
# Done!
# -----------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. EDIT miner_monitor.py and update the configuration section:"
echo "   - TARGET_URL: Your Luxor watcher URL"
echo "   - EXPECTED_WORKERS: Number of miners you have"
echo "   - EMAIL_FROM: Your Gmail address"
echo "   - EMAIL_TO: Where to send alerts"
echo "   - GMAIL_APP_PASSWORD: Your Gmail App Password"
echo "   - COMPANY_NAME: Your company/operation name"
echo ""
echo "2. Make the script executable:"
echo "   chmod +x miner_monitor.py"
echo ""
echo "3. Test it manually:"
echo "   python3 miner_monitor.py"
echo ""
echo "4. Set up hourly cron job (see README.md)"
echo ""
