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
- **Forecast Carousel**: 3-panel hourly and daily forecasts with auto-flipping (10-second intervals)
- **"Weather on the 8s"**: Classic Weather Channel-style interrupts every 10 minutes during forecast mode
- **Scheduled Automation**: Auto-activate forecast at 5 AM (M-F) and 7 AM (Sat-Sun), auto-off at 11 PM
- **Preset Layouts**: Quick access to ON-CALL, FREE, BUSY, QUIET, KNOCK displays
- **Custom Text Formatting**: Multi-line text with customizable colors and sizes
- **Day/Night Mode**: Automatic brightness adjustment based on sunrise/sunset
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
# Adafruit IO Configuration
aio:
  username: "your_aio_username"
  key: "your_aio_key"
  feed: "matrixmessage"
  weather_location_id: 2815  # Your Adafruit IO weather location ID

  # MQTT settings (real-time updates)
  mqtt:
    enabled: true
    broker: "io.adafruit.com"
    port: 1883
    keepalive: 60

  # REST API fallback (used when MQTT disconnected)
  rest:
    enabled: true
    poll_interval: 10  # seconds

# LED Matrix Hardware Configuration
display:
  width: 64
  height: 32
  brightness: 100   # 1-100: Global brightness
  gpio_slowdown: 4  # 0-4: Increase if flickering
  pwm_bits: 11      # 1-11: Color depth (11 = best quality)
  hardware_pulse: true  # true = better display (disables sound)

  # Advanced options (usually don't need to change)
  hardware_mapping: "adafruit-hat-pwm"
  rows: 32
  chain_length: 1
  parallel: 1
  multiplexing: 0

# Forecast Carousel Configuration
forecast:
  flip_interval: 10  # Seconds between hourly/daily view flips

# Day/Night Mode Schedule (fallback when weather unavailable)
schedule:
  enable_auto_dimming: true
  night_start: "22:00"  # 24-hour format
  night_end: "07:00"

# RTC Configuration
rtc:
  enabled: true
  i2c_bus: 1
  address: 0x68
  sync_interval: 3600  # Sync system time from RTC every hour

# Logging
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  file: "/var/log/ledmatrix.log"
  max_size_mb: 10
  backup_count: 3
```

### Day/Night Mode Explained

The display automatically adjusts colors for day and night viewing:

**Primary Mode (Weather-based):**
- Uses sunrise/sunset times from weather data location
- Automatically switches based on actual daylight hours
- Night palette: All colors dimmed to 25% brightness
- Day palette: Full vibrant colors

**Fallback Mode (Schedule-based):**
- Only used when weather data unavailable
- Uses `night_start` and `night_end` times from config
- Requires `enable_auto_dimming: true`

**Note:** Brightness adjustment is done via color palette, not hardware brightness setting. The `brightness` setting remains constant.

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
- `WEATHER` - Display current weather information
- `FORECAST` - Display forecast carousel (hourly/daily auto-flip)
- `OFF` or `BLANK` - Clear display

### Color Palette

Day mode (full brightness):
- 0: Black, 1: White, 2: Red, 3: Green, 4: Blue
- 5: Yellow/Orange, 6: Magenta, 7: Cyan, 8: Orange Red
- 9: Purple, 10: Hot Pink, 11: Lime Green
- 12: Deep Pink, 13: Deep Sky Blue, 14: Gold
- 15-27: Extended palette (orange red, medium purple, medium spring green, tomato, turquoise, orchid, pale green, khaki, plum, sky blue, wheat, light salmon, light sea green)

Night mode automatically dims all colors to 25% brightness (palette-based dimming).

## Forecast Carousel

The `FORECAST` command displays a 3-panel carousel that alternates between hourly and daily forecasts:

**Hourly View (10 seconds):**
- **NOW**: Current temperature, condition, precipitation chance
- **+6H**: 6-hour forecast
- **+12H**: 12-hour forecast

**Daily View (10 seconds):**
- **TODAY**: Current temp, condition, precipitation
- **TMR**: Tomorrow's high/low, condition, precipitation
- **DAY+2**: Day after tomorrow's high/low, condition, precipitation

**Features:**
- Animated progress bar on bottom row (cyan → yellow → orange → red)
- Color-coded temperatures (blue for freezing, green for comfortable, red for hot)
- Abbreviated weather conditions (CLR, PC, RN, SNW, etc.)
- Respects day/night mode for automatic dimming

### "Weather on the 8s"

During `FORECAST` mode, the display automatically interrupts every 10 minutes to show current weather:
- Triggers at :08, :18, :28, :38, :48, :58 of each hour
- Displays current weather with 30-second progress bar
- Automatically resumes forecast carousel after 30 seconds
- Mimics the classic Weather Channel "Local on the 8s" experience

### Scheduled Automation

The display automatically manages itself on a schedule:

**Auto-FORECAST:**
- Monday-Friday: 5:00 AM
- Saturday-Sunday: 7:00 AM

**Auto-OFF:**
- Every day: 11:00 PM

**Startup Behavior:**
- If no command received within 60 seconds of startup, automatically activates FORECAST mode
- Any manual command disables the startup auto-forecast

**Note:** Day/night mode continues to update automatically based on sunrise/sunset times throughout all display modes.

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

- `src/main.py` - Main application entry point, forecast carousel control, scheduled automation
- `src/config.py` - Configuration management and color palettes
- `src/display_manager.py` - RGB matrix display control, forecast rendering, progress bars
- `src/text_renderer.py` - Text formatting and rendering
- `src/aio_client.py` - Adafruit IO MQTT + REST client, weather data parsing
- `src/rtc_sync.py` - RTC time synchronization

## Credits

- RGB Matrix Library: https://github.com/hzeller/rpi-rgb-led-matrix
- Adafruit IO: https://io.adafruit.com
- Original MatrixPortal M4 project

## License

MIT License - See LICENSE file for details
