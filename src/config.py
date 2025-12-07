"""
Configuration management and color palettes
"""

import os
import yaml
import logging
from datetime import datetime, time as dt_time
from pathlib import Path

try:
    from astral import LocationInfo
    from astral.sun import sun
    ASTRAL_AVAILABLE = True
except ImportError:
    ASTRAL_AVAILABLE = False
    logging.warning("astral library not available - sunrise/sunset calculation disabled")


class Config:
    """Application configuration manager"""

    def __init__(self, config_path="config.yaml"):
        self.config_path = Path(config_path)
        self.data = {}
        self._is_night = False
        self.load()
        self._init_palettes()
        self._init_night_mode()

    def load(self):
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Copy config.yaml.example to config.yaml and edit with your settings"
            )

        with open(self.config_path, 'r') as f:
            self.data = yaml.safe_load(f)

        # Validate required fields
        required = ['aio', 'display']
        for field in required:
            if field not in self.data:
                raise ValueError(f"Missing required config section: {field}")

    def _init_palettes(self):
        """Initialize day and night color palettes"""
        # Day palette - Full brightness vibrant colors
        self.day_palette = {
            0: (0, 0, 0),           # Black
            1: (255, 255, 255),     # White
            2: (255, 0, 0),         # Red
            3: (0, 255, 0),         # Green
            4: (0, 0, 255),         # Blue
            5: (255, 128, 0),       # Yellow/Orange
            6: (255, 0, 255),       # Magenta
            7: (0, 255, 255),       # Cyan
            8: (255, 69, 0),        # Orange Red
            9: (128, 0, 255),       # Purple
            10: (255, 105, 180),    # Hot Pink
            11: (50, 205, 50),      # Lime Green
            12: (255, 20, 147),     # Deep Pink
            13: (0, 191, 255),      # Deep Sky Blue
            14: (255, 215, 0),      # Gold
            15: (255, 69, 0),       # Orange Red
            16: (147, 112, 219),    # Medium Purple
            17: (0, 250, 154),      # Medium Spring Green
            18: (255, 99, 71),      # Tomato
            19: (64, 224, 208),     # Turquoise
            20: (218, 112, 214),    # Orchid
            21: (152, 251, 152),    # Pale Green
            22: (240, 230, 140),    # Khaki
            23: (221, 160, 221),    # Plum
            24: (135, 206, 235),    # Sky Blue
            25: (245, 222, 179),    # Wheat
            26: (255, 160, 122),    # Light Salmon
            27: (32, 178, 170),     # Light Sea Green
        }

        # Night palette - Dimmed colors (divide by 4)
        self.night_palette = {
            k: (r // 4, g // 4, b // 4)
            for k, (r, g, b) in self.day_palette.items()
        }

    def get_palette(self):
        """Get current color palette based on day/night mode"""
        return self.night_palette if self._is_night else self.day_palette

    def _init_night_mode(self):
        """Calculate initial night mode at startup based on location and time"""
        if not ASTRAL_AVAILABLE:
            logging.warning("Cannot calculate initial night mode - astral library not available")
            return

        try:
            # Get location from config (use weather location if available)
            location_data = self.data.get('location', {})
            latitude = location_data.get('latitude', 39.03)
            longitude = location_data.get('longitude', -94.68)

            # Calculate sunrise/sunset for today
            location = LocationInfo(latitude=latitude, longitude=longitude)
            s = sun(location.observer, date=datetime.now().date())
            now = datetime.now(s['sunrise'].tzinfo)
            is_night = now < s['sunrise'] or now > s['sunset']

            self._is_night = is_night
            logging.info(f"Initial night mode: {'NIGHT' if is_night else 'DAY'} (sunrise: {s['sunrise'].strftime('%H:%M')}, sunset: {s['sunset'].strftime('%H:%M')}, now: {now.strftime('%H:%M')})")

        except Exception as e:
            logging.error(f"Failed to calculate initial night mode: {e}")
            self._is_night = False

    def set_night_mode(self, is_night):
        """Set day/night mode (called by weather module or scheduler)"""
        self._is_night = is_night

    def is_night_time(self):
        """Check if current time is in night mode based on schedule"""
        if not self.data.get('schedule', {}).get('enable_auto_dimming', True):
            return False

        schedule = self.data.get('schedule', {})
        night_start = schedule.get('night_start', '22:00')
        night_end = schedule.get('night_end', '07:00')

        try:
            now = datetime.now().time()
            start = datetime.strptime(night_start, '%H:%M').time()
            end = datetime.strptime(night_end, '%H:%M').time()

            if start <= end:
                # Same day range (e.g., 22:00 - 23:59)
                return start <= now <= end
            else:
                # Crosses midnight (e.g., 22:00 - 07:00)
                return now >= start or now <= end
        except Exception as e:
            logging.error(f"Error checking night time: {e}")
            return False

    # Convenience accessors
    @property
    def aio_username(self):
        return self.data['aio']['username']

    @property
    def aio_key(self):
        return self.data['aio']['key']

    @property
    def aio_feed(self):
        return self.data['aio'].get('feed', 'matrixmessage')

    @property
    def weather_location_id(self):
        return self.data['aio'].get('weather_location_id', 2815)

    @property
    def mqtt_enabled(self):
        return self.data['aio'].get('mqtt', {}).get('enabled', True)

    @property
    def rest_enabled(self):
        return self.data['aio'].get('rest', {}).get('enabled', True)

    @property
    def rest_poll_interval(self):
        return self.data['aio'].get('rest', {}).get('poll_interval', 10)

    @property
    def display_width(self):
        return self.data['display'].get('width', 64)

    @property
    def display_height(self):
        return self.data['display'].get('height', 32)

    @property
    def gpio_slowdown(self):
        return self.data['display'].get('gpio_slowdown', 4)

    @property
    def pwm_bits(self):
        return self.data['display'].get('pwm_bits', 11)

    @property
    def brightness(self):
        return self.data['display'].get('brightness', 100)

    @property
    def hardware_mapping(self):
        return self.data['display'].get('hardware_mapping', 'adafruit-hat-pwm')

    @property
    def hardware_pulse(self):
        """Enable hardware pulse generation (disables sound compatibility)"""
        return self.data['display'].get('hardware_pulse', True)

    @property
    def rtc_enabled(self):
        return self.data.get('rtc', {}).get('enabled', True)

    @property
    def logging_level(self):
        return self.data.get('logging', {}).get('level', 'INFO')
