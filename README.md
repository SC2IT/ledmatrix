# LED Matrix Display System

Raspberry Pi Zero W 2 + Adafruit RGB Matrix HAT + RTC display controller for 32x64 LED matrices.

## Hardware Requirements

- Raspberry Pi Zero W 2
- Adafruit RGB Matrix HAT with RTC
- 32x64 RGB LED Matrix (HUB75 interface)
- 5V 4A+ power supply

## Features

- **Real-time Updates**: MQTT subscription to Adafruit IO for instant display updates
- **Weather Display**: Automatic weather updates from Adafruit IO Weather service
- **Preset Layouts**: Quick access to ON-CALL, FREE, BUSY, QUIET, KNOCK displays
- **Custom Text Formatting**: Multi-line text with customizable colors and sizes
- **Day/Night Mode**: Automatic brightness adjustment based on time of day
- **RTC Synchronization**: Maintains accurate time even without internet
- **Auto-start**: Systemd service runs display on boot

## Installation

### Quick Install

SSH into your Raspberry Pi and run:

```bash
cd ~
git clone https://github.com/SC2IT/ledmatrix.git
cd ledmatrix
chmod +x install.sh
./install.sh
```

The installer will:
1. Install system dependencies
2. Build and install the RGB matrix library
3. Install Python dependencies
4. Configure the RTC
5. Create configuration file
6. Set up systemd service for auto-start

### Manual Installation

If you prefer manual installation:

```bash
# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev python3-pillow \
    git libatlas-base-dev i2c-tools

# 2. Clone and build RGB matrix library
cd ~
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
make build-python PYTHON=$(which python3)
sudo make install-python PYTHON=$(which python3)

# 3. Install this project
cd ~
git clone https://github.com/SC2IT/ledmatrix.git
cd ledmatrix
pip3 install -r requirements.txt

# 4. Configure
cp config.yaml.example config.yaml
nano config.yaml  # Edit with your settings

# 5. Enable I2C for RTC
sudo raspi-config nonint do_i2c 0

# 6. Set up systemd service
sudo cp ledmatrix.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ledmatrix
sudo systemctl start ledmatrix
```

## Configuration

Edit `config.yaml` with your settings:

```yaml
# Adafruit IO Credentials
aio:
  username: "your_aio_username"
  key: "your_aio_key"
  feed: "matrixmessage"
  weather_location_id: 2815  # Your weather location ID

# Display Settings
display:
  width: 64
  height: 32
  brightness: 100  # 1-100
  gpio_slowdown: 4  # Increase if flickering (4 recommended with sound enabled)

# Day/Night Mode
schedule:
  enable_auto_dimming: true
  day_brightness: 100
  night_brightness: 40
  night_start: "22:00"
  night_end: "07:00"
```

## Usage

### Sending Commands via Adafruit IO

Send text to your Adafruit IO feed to control the display:

**Simple Text:**
```
Hello World
```

**Formatted Text (with colors and sizes):**
```
{2}<3>URGENT
{1}<2>Meeting at 3pm
```

Format: `{color}<size>text`
- Color: 0-27 (see color palette below)
- Size: 1-4 (1=small, 2=medium, 3=large, 4=xlarge)

**Preset Commands:**
- `ON-CALL` - On-Call Urgent Needs Only
- `FREE` - Free But Knock
- `BUSY` - Busy Do Not Enter
- `QUIET` - Quiet Meeting in Progress
- `KNOCK` - Knock Meeting in Progress
- `WEATHER` - Display weather information
- `OFF` or `BLANK` - Clear display

### Color Palette

Day mode (full brightness):
- 0: Black, 1: White, 2: Red, 3: Green, 4: Blue
- 5: Yellow, 6: Magenta, 7: Cyan, 8: Orange
- 9: Purple, 10: Hot Pink, 11: Lime Green
- 12: Deep Pink, 13: Sky Blue, 14: Gold
- 15-27: Extended palette

Night mode automatically dims all colors.

## Service Management

```bash
# Check status
sudo systemctl status ledmatrix

# View logs
sudo journalctl -u ledmatrix -f

# Restart service
sudo systemctl restart ledmatrix

# Stop service
sudo systemctl stop ledmatrix

# Disable auto-start
sudo systemctl disable ledmatrix
```

## Troubleshooting

### Display flickering
- Increase `gpio_slowdown` in config.yaml (try 4 or 5)
- This is normal when sound is enabled

### No display output
- Check power supply (needs 5V 4A minimum)
- Verify connections to HAT
- Check service status: `sudo systemctl status ledmatrix`
- View logs: `sudo journalctl -u ledmatrix -f`

### Weather not updating
- Verify Adafruit IO credentials
- Check weather location ID
- Ensure MQTT connection is working (check logs)

### RTC not syncing
- Enable I2C: `sudo raspi-config`
- Check RTC hardware: `sudo i2cdetect -y 1`
- Should show device at address 0x68

## Development

Run manually for testing:

```bash
cd ~/ledmatrix
python3 -m src.main
```

## Architecture

- `src/main.py` - Main application entry point
- `src/config.py` - Configuration management
- `src/display_manager.py` - RGB matrix display control
- `src/text_renderer.py` - Text formatting and rendering
- `src/weather.py` - Weather data and display
- `src/aio_client.py` - Adafruit IO MQTT + REST client
- `src/rtc_sync.py` - RTC time synchronization

## Credits

- RGB Matrix Library: https://github.com/hzeller/rpi-rgb-led-matrix
- Adafruit IO: https://io.adafruit.com
- Original MatrixPortal M4 project

## License

MIT License - See LICENSE file for details
