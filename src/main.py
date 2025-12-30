#!/usr/bin/env python3
"""
LED Matrix Display System - Main Application
Raspberry Pi Zero W 2 + Adafruit RGB Matrix HAT
"""

import logging
import signal
import sys
import time
from pathlib import Path
from enum import Enum, auto

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.display_manager import DisplayManager
from src.text_renderer import TextParser
from src.aio_client import AIOClient
from src.owm_client import OWMClient
from src.rtc_sync import RTCSync


class DisplayMode(Enum):
    """App display modes - replaces multiple boolean flags with clear state machine"""
    IDLE = auto()  # Nothing displayed or cleared
    TEXT = auto()  # Custom formatted text
    WEATHER = auto()  # Current weather (static)
    FORECAST_HOURLY = auto()  # Hourly forecast carousel
    FORECAST_DAILY = auto()  # Daily forecast carousel
    WEATHER_ON_8S = auto()  # "Weather on the 8s" special display
    PRESET = auto()  # Preset layout (ON-CALL, FREE, BUSY, etc.)


class LEDMatrixApp:
    """Main LED Matrix application"""

    def __init__(self, config_path="config.yaml"):
        """Initialize application"""
        # Load configuration
        self.config = Config(config_path)

        # Setup logging
        self._setup_logging()

        logging.info("=" * 50)
        logging.info("LED Matrix Display System Starting")
        logging.info("=" * 50)

        # Initialize components
        self.display = DisplayManager(self.config)
        self.parser = TextParser()
        self.rtc = RTCSync(self.config)
        self.aio_client = None
        self.weather_client = None

        # State
        self.last_command = None
        self.current_weather = None
        self.running = False
        self.forecast_mode_active = False
        self.forecast_flip_timer = 0.0
        self.last_loop_time = time.time()
        self.startup_time = time.time()
        self.startup_auto_forecast_timeout = 60  # seconds after startup
        self.startup_auto_forecast_enabled = True  # Only auto-forecast once during startup

        # Schedule automation
        self.last_schedule_check_minute = -1  # Track last minute we checked schedules
        self.weather_on_8s_active = False  # "Weather on the 8s" mode
        self.weather_on_8s_timer = 0.0  # Timer for 30-second display
        self.weather_on_8s_duration = 30  # seconds

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _setup_logging(self):
        """Setup logging configuration"""
        log_level = getattr(logging, self.config.logging_level, logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)

        # File handler (if specified)
        log_file = self.config.data.get('logging', {}).get('file')
        handlers = [console_handler]

        if log_file:
            try:
                from logging.handlers import RotatingFileHandler
                max_bytes = self.config.data.get('logging', {}).get('max_size_mb', 10) * 1024 * 1024
                backup_count = self.config.data.get('logging', {}).get('backup_count', 3)

                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=max_bytes,
                    backupCount=backup_count
                )
                file_handler.setLevel(log_level)
                file_handler.setFormatter(console_formatter)
                handlers.append(file_handler)
            except Exception as e:
                print(f"Warning: Could not setup file logging: {e}")

        # Configure root logger directly (basicConfig doesn't work if logging already initialized)
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        # Clear any existing handlers
        root_logger.handlers.clear()
        # Add our handlers
        for handler in handlers:
            root_logger.addHandler(handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logging.info(f"Received signal {signum}, shutting down...")
        self.shutdown()
        sys.exit(0)

    def _on_command_received(self, message: dict):
        """Handle command from Adafruit IO"""
        command = message.get('value', '').strip()
        source = message.get('source', 'unknown')

        if not command:
            return

        # Avoid processing duplicate commands
        if command == self.last_command:
            logging.debug(f"Duplicate command ignored: {command}")
            return

        self.last_command = command
        self.startup_auto_forecast_enabled = False  # Disable startup auto-forecast after first command
        logging.info(f"Command received ({source}): {command}")

        # Process command
        self._process_command(command)

    def _process_command(self, command: str):
        """Process and display command"""
        try:
            # Special commands
            cmd_upper = command.upper().strip()

            if cmd_upper in ["OFF", "BLANK", "SCREEN OFF"]:
                logging.info("Clearing display")
                self.forecast_mode_active = False
                self.display.clear()

            elif cmd_upper == "WEATHER":
                logging.info("Displaying weather")
                self.forecast_mode_active = False
                if self.current_weather:
                    condition = self.current_weather.get('condition', 'Clear')
                    self.display.show_weather(self.current_weather, condition)
                else:
                    self.display.show_simple_message("Weather", "Waiting...")

            elif cmd_upper == "FORECAST":
                logging.info("Displaying forecast carousel")
                self.forecast_mode_active = True
                self.forecast_flip_timer = 0.0
                self.last_loop_time = time.time()
                self.display.carousel_needs_redraw = True  # Trigger initial full redraw
                self.display.carousel_clear_frames = 2  # Clear both buffers to prevent flickering
                # Initial display will happen in main loop

            elif cmd_upper in ["ON-CALL", "FREE", "BUSY", "QUIET", "KNOCK"]:
                logging.info(f"Displaying preset: {cmd_upper}")
                self.forecast_mode_active = False
                self.display.show_preset(cmd_upper)

            else:
                # Parse and display formatted text
                logging.info("Displaying formatted text")
                self.forecast_mode_active = False
                parsed = self.parser.parse(command)

                if parsed:
                    self.display.show_text(parsed)
                else:
                    self.display.show_simple_message("No Content")

        except Exception as e:
            logging.error(f"Error processing command: {e}", exc_info=True)
            self.display.show_simple_message("Error", str(e)[:12])

    def _on_weather_update(self, weather_data: dict):
        """Handle weather update"""
        self.current_weather = weather_data
        logging.debug(f"Weather updated: {weather_data.get('temp')}°F")

        # If currently showing weather, refresh display
        if self.last_command and self.last_command.upper() == "WEATHER":
            condition = weather_data.get('condition', 'Clear')
            self.display.show_weather(weather_data, condition)

    def start(self):
        """Start the application"""
        logging.info("Starting application components...")

        # Start RTC sync
        if self.config.rtc_enabled:
            self.rtc.start_auto_sync()

        # Initialize Adafruit IO client
        self.aio_client = AIOClient(self.config, on_message_callback=self._on_command_received)
        self.aio_client.start()

        # Initialize OpenWeatherMap client
        self.weather_client = OWMClient(self.config, on_weather_callback=self._on_weather_update)
        self.weather_client.start()

        # Wait for weather data to load (up to 60 seconds)
        self.running = True
        logging.info("Waiting for weather data...")
        self._wait_for_weather_data()

        logging.info("Application started successfully")

        # Log status
        aio_status = self.aio_client.get_status()
        logging.info(f"AIO Status: {aio_status}")

        # Main loop
        self._main_loop()

    def _check_scheduled_automation(self):
        """Check and execute scheduled automation tasks"""
        from datetime import datetime

        now = datetime.now()
        current_minute = now.hour * 60 + now.minute  # Minutes since midnight

        # Only check once per minute
        if current_minute == self.last_schedule_check_minute:
            return
        self.last_schedule_check_minute = current_minute

        # Auto-FORECAST schedule
        # Monday-Friday at 5:00 AM
        if now.weekday() < 5 and now.hour == 5 and now.minute == 0:
            logging.info("Scheduled auto-FORECAST: 5 AM weekday")
            self.forecast_mode_active = True
            self.forecast_flip_timer = 0.0
            self.display.carousel_needs_redraw = True  # Trigger initial full redraw
            self.display.carousel_clear_frames = 2  # Clear both buffers
            return

        # Saturday-Sunday at 7:00 AM
        if now.weekday() >= 5 and now.hour == 7 and now.minute == 0:
            logging.info("Scheduled auto-FORECAST: 7 AM weekend")
            self.forecast_mode_active = True
            self.forecast_flip_timer = 0.0
            self.display.carousel_needs_redraw = True  # Trigger initial full redraw
            self.display.carousel_clear_frames = 2  # Clear both buffers
            return

        # Auto-OFF at 11:00 PM (23:00) daily
        if now.hour == 23 and now.minute == 0:
            logging.info("Scheduled auto-OFF: 11 PM")
            self.forecast_mode_active = False
            self.display.clear()
            return

    def _check_weather_on_8s(self):
        """Check if it's time for 'Weather on the 8s' display"""
        from datetime import datetime

        now = datetime.now()
        minute = now.minute

        # Check if minute ends in 8 (08, 18, 28, 38, 48, 58)
        if minute % 10 == 8 and not self.weather_on_8s_active:
            # Only trigger once per "8" minute
            if not hasattr(self, '_last_8s_minute') or self._last_8s_minute != minute:
                logging.info(f"Weather on the 8s triggered at {now.strftime('%H:%M')}")
                self.weather_on_8s_active = True
                self.weather_on_8s_timer = 0.0
                self._last_8s_minute = minute

    def _wait_for_weather_data(self):
        """Wait up to 60 seconds for weather data to load"""
        max_wait = 60  # seconds
        check_interval = 1  # seconds
        elapsed = 0

        while elapsed < max_wait and self.running:
            # Check if we have weather data
            has_current = self.current_weather is not None
            has_hourly = len(self.weather_client.get_hourly_forecasts()) > 0 if self.weather_client else False
            has_daily = len(self.weather_client.get_daily_forecasts()) > 0 if self.weather_client else False

            if has_current and has_hourly and has_daily:
                logging.info(f"Weather data loaded after {elapsed} seconds")
                self.display.show_simple_message("Weather", "Loaded!")
                time.sleep(1)
                return

            # Update loading display
            dots = "." * ((elapsed % 4) + 1)
            self.display.show_simple_message("Loading", f"Weather{dots}")

            time.sleep(check_interval)
            elapsed += check_interval

        # Timeout or interrupted
        if elapsed >= max_wait:
            logging.warning("Weather data loading timeout after 60 seconds")
            self.display.show_simple_message("Timeout", "Starting...")
            time.sleep(2)
        else:
            logging.info("Weather data wait interrupted")

    def _main_loop(self):
        """Main application loop"""
        rest_poll_interval = self.config.rest_poll_interval

        while self.running:
            try:
                # Calculate delta time
                current_time = time.time()
                delta_time = current_time - self.last_loop_time
                self.last_loop_time = current_time

                # Poll REST API if MQTT not connected (fallback)
                if not self.aio_client.mqtt_connected and self.aio_client.rest_enabled:
                    message = self.aio_client.poll_rest_api()
                    if message:
                        self._on_command_received(message)

                # Check scheduled automation (daily schedules)
                self._check_scheduled_automation()

                # Check for startup auto-forecast (only once, within first 60s after startup)
                time_since_startup = current_time - self.startup_time
                if (self.startup_auto_forecast_enabled and
                    not self.forecast_mode_active and
                    time_since_startup >= self.startup_auto_forecast_timeout):
                    logging.info(f"Auto-activating FORECAST mode after {self.startup_auto_forecast_timeout}s startup period")
                    self.forecast_mode_active = True
                    self.forecast_flip_timer = 0.0
                    self.display.carousel_needs_redraw = True  # Trigger initial full redraw
                    self.display.carousel_clear_frames = 2  # Clear both buffers
                    self.startup_auto_forecast_enabled = False  # Disable after first use

                # Update forecast carousel if active
                if self.forecast_mode_active:
                    # Check for "Weather on the 8s" trigger
                    self._check_weather_on_8s()

                    if self.weather_on_8s_active:
                        # Show current weather with progress bar for 30 seconds
                        self.weather_on_8s_timer += delta_time

                        if self.current_weather:
                            # Render weather display with "on the 8s" progress bar
                            self.display.show_weather_with_progress(
                                self.current_weather,
                                self.current_weather.get('condition', 'Clear'),
                                self.weather_on_8s_timer,
                                self.weather_on_8s_duration
                            )

                        # Check if time to resume forecast
                        if self.weather_on_8s_timer >= self.weather_on_8s_duration:
                            logging.info("Weather on the 8s complete, resuming FORECAST")
                            self.weather_on_8s_active = False
                            self.weather_on_8s_timer = 0.0
                    else:
                        # Normal forecast carousel
                        self.forecast_flip_timer += delta_time

                        # Render carousel with current progress
                        hourly = self.weather_client.get_hourly_forecasts() if self.weather_client else {}
                        daily = self.weather_client.get_daily_forecasts() if self.weather_client else {}

                        self.display.show_forecast_carousel(
                            self.current_weather or {},
                            hourly,
                            daily,
                            self.forecast_flip_timer
                        )

                        # Check if time to flip (after displaying full bar)
                        if self.forecast_flip_timer >= self.config.forecast_flip_interval:
                            logging.info(f"Flipping forecast view (timer={self.forecast_flip_timer:.1f}s >= interval={self.config.forecast_flip_interval}s)")
                            self.display.flip_carousel_view()
                            self.forecast_flip_timer = 0.0
                        else:
                            logging.debug(f"Forecast timer: {self.forecast_flip_timer:.1f}s / {self.config.forecast_flip_interval}s")

                # Update day/night mode based on time
                if self.config.data.get('schedule', {}).get('enable_auto_dimming', True):
                    is_night = self.config.is_night_time()
                    if is_night != self.config._is_night:
                        self.config.set_night_mode(is_night)
                        logging.info(f"Mode changed: {'Night' if is_night else 'Day'}")

                        # Refresh display if showing weather
                        if self.last_command and self.last_command.upper() == "WEATHER" and self.current_weather:
                            condition = self.current_weather.get('condition', 'Clear')
                            self.display.show_weather(self.current_weather, condition)

                # Sleep
                time.sleep(1)

            except KeyboardInterrupt:
                logging.info("Keyboard interrupt received")
                break
            except Exception as e:
                logging.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(5)

        self.shutdown()

    def shutdown(self):
        """Shutdown application"""
        if not self.running:
            return

        logging.info("Shutting down application...")
        self.running = False

        # Stop components
        if self.aio_client:
            self.aio_client.stop()

        if self.weather_client:
            self.weather_client.stop()

        if self.rtc:
            self.rtc.stop()

        # Clear display
        try:
            self.display.clear()
        except:
            pass

        logging.info("Application shutdown complete")


def main():
    """Main entry point"""
    # Change to script directory
    script_dir = Path(__file__).parent.parent
    import os
    os.chdir(script_dir)

    try:
        app = LEDMatrixApp()
        app.start()
    except KeyboardInterrupt:
        logging.info("Application interrupted")
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
