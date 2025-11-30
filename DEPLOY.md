# Deployment Guide

## Pushing to GitHub Repository

### 1. Initialize Git Repository (if not already done)

```bash
cd "E:\You Suck Dropbox\Sean Cummings\Projects\Matrix Portal M4 Adafruit-IO StreamDeck Project\ledmatrix"
git init
```

### 2. Add Remote Repository

```bash
git remote add origin https://github.com/SC2IT/ledmatrix.git
```

### 3. Stage All Files

```bash
git add .
```

### 4. Create Initial Commit

```bash
git commit -m "Initial commit: Complete rewrite for Raspberry Pi Zero W 2

- Migrated from MatrixPortal M4 (CircuitPython) to Pi Zero W 2 (Python 3)
- Implemented MQTT + REST API client for Adafruit IO
- Added RTC synchronization support
- Integrated weather display via Adafruit IO Weather
- Created systemd service for auto-start
- Added comprehensive documentation

Features:
- Real-time MQTT updates (instant commands)
- REST API fallback for reliability
- Weather display with auto day/night mode
- Preset layouts (ON-CALL, FREE, BUSY, QUIET, KNOCK)
- Custom text formatting with colors and sizes
- RTC time synchronization
- Configurable brightness by time of day
- Automatic restart on failure

Hardware:
- Raspberry Pi Zero W 2
- Adafruit RGB Matrix HAT with RTC
- 32x64 RGB LED Matrix
"
```

### 5. Push to GitHub

```bash
git branch -M main
git push -u origin main
```

If you encounter issues with existing content:
```bash
git pull origin main --allow-unrelated-histories
git push -u origin main
```

## Project Structure

```
ledmatrix/
├── README.md              # Main documentation
├── QUICKSTART.md          # Quick installation guide
├── MIGRATION.md           # Migration from MatrixPortal M4
├── DEPLOY.md             # This file
├── requirements.txt       # Python dependencies
├── config.yaml.example    # Configuration template
├── install.sh            # Installation script
├── .gitignore            # Git ignore rules
├── src/
│   ├── __init__.py       # Package initialization
│   ├── main.py           # Main application entry point
│   ├── config.py         # Configuration management
│   ├── display_manager.py # RGB matrix display control
│   ├── text_renderer.py  # Text formatting and parsing
│   ├── aio_client.py     # Adafruit IO MQTT + REST client
│   └── rtc_sync.py       # RTC time synchronization
├── fonts/                # TrueType fonts (empty - add your own)
├── icons/                # Weather icons (empty - add your own)
└── backup/               # Backup files (not in git)
```

## Files NOT in Git

The following are excluded via `.gitignore`:

- `config.yaml` - Contains secrets (AIO credentials)
- `backup/` - Your original MatrixPortal files
- `*.log` - Log files
- `__pycache__/` - Python cache files

## What Your Pi Will Need

After cloning the repository on your Raspberry Pi, you'll need to:

1. **Run the installer:**
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

2. **Create config.yaml:**
   ```bash
   cp config.yaml.example config.yaml
   nano config.yaml
   # Edit with your AIO credentials
   ```

3. **Reboot:**
   ```bash
   sudo reboot
   ```

## Optional: Add Fonts and Icons

### Adding Custom Fonts

1. Download TrueType (.ttf) fonts
2. Copy to `fonts/` directory
3. The display manager will automatically use them

```bash
# On your Pi
cd ~/ledmatrix/fonts
wget https://example.com/your-font.ttf
```

### Adding Weather Icons

1. Create 24x24 PNG images for each weather condition
2. Name them: `clear.png`, `cloudy.png`, `rain.png`, etc.
3. Copy to `icons/` directory

```bash
# On your Pi
cd ~/ledmatrix/icons
# Copy your icon files here
```

## Updating the Code

### From Your PC

1. Make changes locally
2. Commit: `git commit -am "Description of changes"`
3. Push: `git push`

### On Your Pi

```bash
cd ~/ledmatrix
git pull
sudo systemctl restart ledmatrix
```

## Creating Releases

When you're ready to create a versioned release:

```bash
git tag -a v1.0.0 -m "Version 1.0.0 - Initial Raspberry Pi release"
git push origin v1.0.0
```

Then create a release on GitHub with release notes.

## Branches Strategy

Suggested workflow:

- `main` - Stable, production-ready code
- `dev` - Development branch for testing
- Feature branches - For specific new features

```bash
# Create development branch
git checkout -b dev
git push -u origin dev

# Create feature branch
git checkout -b feature/new-animation
# Make changes
git commit -am "Add new animation feature"
git push -u origin feature/new-animation
```

## Continuous Integration (Optional)

You could add GitHub Actions for:
- Code linting (pylint, flake8)
- Unit tests
- Automatic deployment to Pi

## Backup Strategy

Your original MatrixPortal M4 files are backed up in:
```
backup/migration_2025-11-29_181712/
```

These are excluded from git (via .gitignore) but safe on your PC.

## Support and Issues

- Create issues: https://github.com/SC2IT/ledmatrix/issues
- Wiki: https://github.com/SC2IT/ledmatrix/wiki
- Discussions: https://github.com/SC2IT/ledmatrix/discussions
