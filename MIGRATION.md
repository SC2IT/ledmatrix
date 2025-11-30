# Migration Guide: MatrixPortal M4 → Raspberry Pi Zero W 2

## Overview

This document explains the migration from the CircuitPython-based MatrixPortal M4 system to the new Python-based Raspberry Pi Zero W 2 system.

## What Changed

### Hardware
- **Old:** MatrixPortal M4 (SAMD51 microcontroller)
- **New:** Raspberry Pi Zero W 2 (ARM Cortex-A53, 512MB RAM)

### Software
- **Old:** CircuitPython 10
- **New:** Python 3.11+ on Linux

### Key Improvements

1. **Real-time MQTT** instead of 10-second polling
2. **Better performance** - 2600x more RAM, faster processor
3. **RTC built into HAT** - accurate timekeeping without internet
4. **Better error handling** - logging, automatic restart
5. **Easier development** - full Python ecosystem, SSH access

## Feature Parity

All original features have been preserved:

| Feature | MatrixPortal M4 | Raspberry Pi |
|---------|----------------|--------------|
| Adafruit IO commands | ✅ | ✅ |
| Weather display | ✅ | ✅ |
| Preset layouts | ✅ | ✅ |
| Custom text formatting | ✅ | ✅ |
| Day/night mode | ✅ | ✅ |
| Color palettes | ✅ | ✅ |
| Auto-start on boot | ✅ | ✅ |
| RTC support | ❌ | ✅ |
| MQTT real-time | ❌ | ✅ |

## Architecture Comparison

### Old (MatrixPortal M4)
```
code.py (main loop)
├── config.py (settings)
├── display_core.py (LED control)
├── text_parser.py (text formatting)
└── weather_module.py (weather via MQTT)
```

### New (Raspberry Pi)
```
src/main.py (application)
├── src/config.py (settings from YAML)
├── src/display_manager.py (RGB matrix via PIL)
├── src/text_renderer.py (text formatting)
├── src/aio_client.py (MQTT + REST for commands)
├── src/weather.py (integrated in aio_client)
└── src/rtc_sync.py (RTC time sync)
```

## Code Migration Details

### Configuration

**Old:** `settings.toml` (CircuitPython)
```toml
CIRCUITPY_AIO_USERNAME = "username"
CIRCUITPY_AIO_KEY = "key"
```

**New:** `config.yaml` (more flexible)
```yaml
aio:
  username: "username"
  key: "key"
  weather_location_id: 2815
display:
  width: 64
  height: 32
  gpio_slowdown: 4
```

### Display Management

**Old:** Used `displayio` and `adafruit_display_text`
```python
from adafruit_display_text import label
lbl = label.Label(font, text="Hello", color=0xFF0000)
```

**New:** Uses PIL (Pillow) for rendering
```python
from PIL import Image, ImageDraw, ImageFont
draw.text((x, y), "Hello", font=font, fill=(255, 0, 0))
```

### Network Communication

**Old:** Polling REST API every 10 seconds
```python
response = matrixportal.network.fetch(url)
data = response.json()
```

**New:** MQTT with REST fallback
```python
# MQTT subscription (real-time)
aio_client = AIOClient(config, callback)
# Automatic fallback to REST if MQTT fails
```

### Weather

**Old:** Direct MQTT subscription in weather_module.py
**New:** Integrated into WeatherClient class with automatic parsing

## Configuration Options

### GPIO Slowdown (Important!)

Since you're **NOT disabling sound**, the GPIO slowdown parameter is critical:

```yaml
display:
  gpio_slowdown: 4  # Recommended value with sound enabled
```

If you see flickering, try values 4-6. Higher = less flickering but slower refresh.

### Brightness Control

**Old:** Hardcoded in palette
**New:** Configurable per mode
```yaml
schedule:
  enable_auto_dimming: true
  day_brightness: 100
  night_brightness: 40
```

## Command Compatibility

All original commands work exactly the same:

```
Simple text:
  Hello World

Formatted text:
  {2}<3>URGENT
  {1}<2>Meeting at 3pm

Presets:
  ON-CALL
  FREE
  BUSY
  QUIET
  KNOCK
  WEATHER

Control:
  OFF
  BLANK
```

## New Capabilities

### 1. Real-time Updates
Commands appear instantly via MQTT (no 10-second delay)

### 2. RTC Support
Accurate time even without internet connection

### 3. Better Logging
```bash
# View live logs
sudo journalctl -u ledmatrix -f

# Search logs
sudo journalctl -u ledmatrix | grep ERROR
```

### 4. Service Management
```bash
sudo systemctl status ledmatrix
sudo systemctl restart ledmatrix
```

### 5. Remote Development
SSH into Pi, edit files, test immediately

## Deployment Workflow

### Old (MatrixPortal M4)
1. Edit files on PC
2. Copy to CIRCUITPY drive
3. Wait for auto-reload
4. Check serial output

### New (Raspberry Pi)
1. SSH into Pi: `ssh pi@raspberrypi.local`
2. Edit files: `nano ~/ledmatrix/src/main.py`
3. Restart service: `sudo systemctl restart ledmatrix`
4. View logs: `sudo journalctl -u ledmatrix -f`

Or use Git:
1. Edit locally and push to GitHub
2. SSH to Pi: `cd ~/ledmatrix && git pull`
3. Restart: `sudo systemctl restart ledmatrix`

## Troubleshooting

### "Module not found" errors
```bash
cd ~/ledmatrix
pip3 install -r requirements.txt
```

### Display flickering
Increase `gpio_slowdown` in config.yaml

### MQTT not connecting
- Check credentials in config.yaml
- Check network: `ping io.adafruit.com`
- View logs: `sudo journalctl -u ledmatrix -f`

### Service won't start
```bash
# Check status
sudo systemctl status ledmatrix

# View errors
sudo journalctl -u ledmatrix -n 50

# Test manually
cd ~/ledmatrix
python3 -m src.main
```

## Performance Comparison

| Metric | MatrixPortal M4 | Raspberry Pi Zero W 2 |
|--------|----------------|----------------------|
| RAM | 192 KB | 512 MB |
| CPU Speed | 120 MHz | 1 GHz (quad-core) |
| Command latency | 10 seconds (polling) | ~1 second (MQTT) |
| Boot time | 5 seconds | 30 seconds |
| Power consumption | ~200mA | ~500mA |

## Next Steps

1. **Test the installation** - Run through QUICKSTART.md
2. **Verify all features** - Test each preset, weather, custom text
3. **Optimize settings** - Adjust brightness, GPIO slowdown
4. **Monitor logs** - Watch for any errors or issues
5. **Customize** - Add custom fonts, icons, features

## Support

- Full documentation: [README.md](README.md)
- Quick start: [QUICKSTART.md](QUICKSTART.md)
- GitHub: https://github.com/SC2IT/ledmatrix
