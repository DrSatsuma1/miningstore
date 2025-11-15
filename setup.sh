#!/bin/bash
# Setup script for Miner Monitor on Linux VPS

echo "=========================================="
echo "Luxor Miner Monitor - Installation Script"
echo "=========================================="
echo ""

# Update package list
echo "[1/5] Updating package list..."
sudo apt-get update

# Install Python3 and pip if not already installed
echo "[2/5] Installing Python3 and pip..."
sudo apt-get install -y python3 python3-pip

# Install Chrome and ChromeDriver for Selenium
echo "[3/5] Installing Google Chrome..."
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
sudo apt-get update
sudo apt-get install -y google-chrome-stable

# Install ChromeDriver
echo "[4/5] Installing ChromeDriver..."
CHROME_DRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE)
wget -N https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip -P /tmp
unzip -o /tmp/chromedriver_linux64.zip -d /tmp
sudo mv /tmp/chromedriver /usr/local/bin/chromedriver
sudo chmod +x /usr/local/bin/chromedriver
rm /tmp/chromedriver_linux64.zip

# Install Python dependencies
echo "[5/5] Installing Python packages..."
pip3 install selenium

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Copy miner_monitor.py to your VPS"
echo "2. Make it executable: chmod +x miner_monitor.py"
echo "3. Test it: python3 miner_monitor.py"
echo "4. Set up cron job to run hourly"
echo ""
