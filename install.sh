#!/bin/bash
# LED Matrix Display System - Installation Script
# For Raspberry Pi Zero W 2 + Adafruit RGB Matrix HAT

set -e  # Exit on error

echo "========================================="
echo "LED Matrix Display System - Installer"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "ERROR: Please run as normal user (not sudo)"
    echo "The script will ask for sudo when needed"
    exit 1
fi

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "WARNING: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Step 1: Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

echo ""
echo "Step 2: Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    python3-dev \
    python3-pillow \
    git \
    libatlas-base-dev \
    i2c-tools \
    build-essential \
    libgraphicsmagick++-dev \
    libwebp-dev

echo ""
echo "Step 3: Enabling I2C for RTC..."
sudo raspi-config nonint do_i2c 0

echo ""
echo "Step 4: Installing RGB LED Matrix library..."
MATRIX_DIR="$HOME/rpi-rgb-led-matrix"

if [ -d "$MATRIX_DIR" ]; then
    echo "RGB matrix library already exists, updating..."
    cd "$MATRIX_DIR"
    git pull
else
    echo "Cloning RGB matrix library..."
    cd "$HOME"
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd "$MATRIX_DIR"
fi

echo "Building RGB matrix library..."
make build-python PYTHON=$(which python3)
echo "Installing RGB matrix library..."
sudo make install-python PYTHON=$(which python3)

echo ""
echo "Step 5: Installing Python dependencies..."
cd "$(dirname "$0")"
pip3 install --upgrade pip
pip3 install -r requirements.txt

echo ""
echo "Step 6: Setting up configuration..."
if [ ! -f config.yaml ]; then
    cp config.yaml.example config.yaml
    echo "Created config.yaml from template"
    echo ""
    echo "IMPORTANT: Edit config.yaml with your Adafruit IO credentials:"
    echo "  nano config.yaml"
    echo ""
    read -p "Press Enter to edit config now, or Ctrl+C to skip..."
    nano config.yaml
else
    echo "config.yaml already exists, skipping..."
fi

echo ""
echo "Step 7: Setting up RTC..."
echo "Checking for RTC at address 0x68..."
if sudo i2cdetect -y 1 | grep -q " 68 "; then
    echo "RTC detected!"

    # Load RTC module
    echo "ds1307" | sudo tee /etc/modules-load.d/rtc.conf > /dev/null

    # Add to /boot/config.txt if not already there
    if ! grep -q "^dtoverlay=i2c-rtc,ds1307" /boot/config.txt 2>/dev/null; then
        echo "dtoverlay=i2c-rtc,ds1307" | sudo tee -a /boot/config.txt > /dev/null
        echo "Added RTC overlay to /boot/config.txt"
    fi
else
    echo "WARNING: RTC not detected at 0x68"
    echo "This is OK if you haven't connected the HAT yet"
fi

echo ""
echo "Step 8: Creating systemd service..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo tee /etc/systemd/system/ledmatrix.service > /dev/null <<EOF
[Unit]
Description=LED Matrix Display System
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 -m src.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo ""
echo "Step 9: Enabling service..."
sudo systemctl enable ledmatrix

echo ""
echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Ensure config.yaml has your Adafruit IO credentials"
echo "2. Connect your LED matrix to the HAT"
echo "3. Reboot your Pi: sudo reboot"
echo ""
echo "After reboot, the display will start automatically."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status ledmatrix   # Check status"
echo "  sudo journalctl -u ledmatrix -f   # View logs"
echo "  sudo systemctl restart ledmatrix  # Restart service"
echo ""
echo "For testing without reboot:"
echo "  sudo systemctl start ledmatrix"
echo ""
