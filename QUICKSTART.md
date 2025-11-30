# Quick Start Guide

## Prerequisites

1. Raspberry Pi Zero W 2 with Raspberry Pi OS Lite installed
2. Adafruit RGB Matrix HAT with RTC installed on Pi
3. 32x64 RGB LED Matrix connected to HAT
4. 5V 4A power supply
5. Network connectivity (WiFi configured)

## Installation Steps

### 1. SSH into your Raspberry Pi

```bash
ssh pi@raspberrypi.local
```

### 2. Clone and Install

```bash
cd ~
git clone https://github.com/SC2IT/ledmatrix.git
cd ledmatrix
chmod +x install.sh
./install.sh
```

The installer will:
- Install all dependencies
- Build the RGB matrix library
- Configure I2C for RTC
- Set up the systemd service

### 3. Configure Adafruit IO Credentials

```bash
nano config.yaml
```

Edit these lines with your credentials:
```yaml
aio:
  username: "YOUR_AIO_USERNAME"
  key: "YOUR_AIO_KEY"
  weather_location_id: 2815  # Your weather location ID
```

Save with `Ctrl+O`, then `Enter`, then `Ctrl+X` to exit.

### 4. Reboot

```bash
sudo reboot
```

After reboot, the display should automatically start and show "Connected - Ready".

## Testing

### Check Service Status

```bash
sudo systemctl status ledmatrix
```

### View Live Logs

```bash
sudo journalctl -u ledmatrix -f
```

### Test Display Manually

```bash
cd ~/ledmatrix
python3 -m src.main
```

Press `Ctrl+C` to stop.

### Send Test Command via Adafruit IO

1. Go to https://io.adafruit.com
2. Open your "matrixmessage" feed
3. Send a test message:
   - Simple text: `Hello World`
   - Formatted: `{2}<3>URGENT\n{1}<2>Meeting at 3pm`
   - Preset: `BUSY`
   - Weather: `WEATHER`

## Command Reference

### Simple Commands
- `WEATHER` - Display weather
- `ON-CALL` - On-Call Urgent Needs Only
- `FREE` - Free But Knock
- `BUSY` - Busy Do Not Enter
- `QUIET` - Quiet Meeting in Progress
- `KNOCK` - Knock Meeting in Progress
- `OFF` or `BLANK` - Clear display

### Formatted Text

Format: `{color}<size>text`

Example:
```
{2}<3>URGENT
{1}<2>Meeting in 5 min
{7}<1>Conference Room A
```

**Colors:**
- 0: Black, 1: White, 2: Red, 3: Green, 4: Blue
- 5: Yellow, 6: Magenta, 7: Cyan, 8: Orange
- 9: Purple, 10: Hot Pink, 11: Lime Green
- etc. (see README for full palette)

**Sizes:**
- 1: Small (6px)
- 2: Medium (8px)
- 3: Large (12px)
- 4: XLarge (16px)

## Troubleshooting

### Display Not Working

```bash
# Check service
sudo systemctl status ledmatrix

# Check logs
sudo journalctl -u ledmatrix -n 50

# Test manually
cd ~/ledmatrix
python3 -m src.main
```

### Flickering Display

Edit `config.yaml`:
```yaml
display:
  gpio_slowdown: 5  # Increase this value (try 4, 5, or 6)
```

Then restart:
```bash
sudo systemctl restart ledmatrix
```

### Weather Not Updating

- Verify Adafruit IO credentials in config.yaml
- Check weather location ID is correct
- Check logs for MQTT connection errors

### RTC Not Working

```bash
# Check I2C is enabled
sudo raspi-config
# Navigate to: Interface Options > I2C > Enable

# Check for RTC
sudo i2cdetect -y 1
# Should show "68"

# Reboot
sudo reboot
```

## Service Management

```bash
# Start
sudo systemctl start ledmatrix

# Stop
sudo systemctl stop ledmatrix

# Restart
sudo systemctl restart ledmatrix

# Disable auto-start
sudo systemctl disable ledmatrix

# Enable auto-start
sudo systemctl enable ledmatrix

# View logs
sudo journalctl -u ledmatrix -f
```

## Next Steps

- Customize colors in `config.yaml`
- Adjust brightness for day/night modes
- Set up custom display schedules
- Add custom fonts to `fonts/` directory
- Add weather icons to `icons/` directory

## Getting Help

- Check full documentation: [README.md](README.md)
- View logs: `sudo journalctl -u ledmatrix -f`
- GitHub Issues: https://github.com/SC2IT/ledmatrix/issues
