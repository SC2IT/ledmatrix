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

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.display_manager import DisplayManager
from src.text_renderer import TextParser
from src.aio_client import AIOClient, WeatherClient
from src.rtc_sync import RTCSync


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

        # Configure root logger
        logging.basicConfig(
            level=log_level,
            handlers=handlers
        )

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

        # Initialize Weather client
        self.weather_client = WeatherClient(self.config, on_weather_callback=self._on_weather_update)

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

                # Update forecast carousel if active
                if self.forecast_mode_active:
                    self.forecast_flip_timer += delta_time

                    # Check if time to flip
                    if self.forecast_flip_timer >= self.config.forecast_flip_interval:
                        self.display.flip_carousel_view()
                        self.forecast_flip_timer = 0.0

                    # Render carousel
                    hourly = self.weather_client.get_hourly_forecasts() if self.weather_client else {}
                    daily = self.weather_client.get_daily_forecasts() if self.weather_client else {}

                    self.display.show_forecast_carousel(
                        self.current_weather or {},
                        hourly,
                        daily,
                        self.forecast_flip_timer
                    )

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
