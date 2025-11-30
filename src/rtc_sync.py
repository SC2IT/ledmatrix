"""
RTC (Real-Time Clock) synchronization
For Adafruit RGB Matrix HAT with RTC
"""

import logging
import subprocess
import time
from datetime import datetime
from threading import Thread, Event


class RTCSync:
    """RTC synchronization manager"""

    def __init__(self, config):
        """
        Initialize RTC sync

        Args:
            config: Config object
        """
        self.config = config
        self.enabled = config.rtc_enabled
        self.running = False
        self.stop_event = Event()
        self.sync_thread = None

        if self.enabled:
            self._check_rtc_available()

    def _check_rtc_available(self):
        """Check if RTC hardware is available"""
        try:
            # Check for RTC device
            result = subprocess.run(
                ['i2cdetect', '-y', '1'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if '68' in result.stdout:
                logging.info("RTC detected at address 0x68")
                return True
            else:
                logging.warning("RTC not detected at 0x68")
                self.enabled = False
                return False

        except Exception as e:
            logging.error(f"Could not check for RTC: {e}")
            self.enabled = False
            return False

    def sync_from_rtc(self):
        """Sync system time from RTC"""
        if not self.enabled:
            return False

        try:
            # Read RTC time
            result = subprocess.run(
                ['sudo', 'hwclock', '-r'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                rtc_time = result.stdout.strip()
                logging.debug(f"RTC time: {rtc_time}")

                # Set system time from RTC
                result = subprocess.run(
                    ['sudo', 'hwclock', '-s'],
                    capture_output=True,
                    timeout=5
                )

                if result.returncode == 0:
                    logging.info("System time synced from RTC")
                    return True
                else:
                    logging.error("Failed to sync system time from RTC")
                    return False
            else:
                logging.error("Failed to read RTC")
                return False

        except Exception as e:
            logging.error(f"RTC sync error: {e}")
            return False

    def sync_to_rtc(self):
        """Sync RTC from system time"""
        if not self.enabled:
            return False

        try:
            # Write system time to RTC
            result = subprocess.run(
                ['sudo', 'hwclock', '-w'],
                capture_output=True,
                timeout=5
            )

            if result.returncode == 0:
                logging.info("RTC synced from system time")
                return True
            else:
                logging.error("Failed to sync RTC from system time")
                return False

        except Exception as e:
            logging.error(f"RTC write error: {e}")
            return False

    def start_auto_sync(self):
        """Start automatic RTC synchronization"""
        if not self.enabled:
            logging.info("RTC sync disabled in config")
            return

        self.running = True
        self.sync_thread = Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        logging.info("RTC auto-sync started")

    def _sync_loop(self):
        """Background sync loop"""
        sync_interval = self.config.data.get('rtc', {}).get('sync_interval', 3600)

        # Initial sync from RTC on startup
        self.sync_from_rtc()

        while self.running and not self.stop_event.is_set():
            # Wait for interval
            self.stop_event.wait(sync_interval)

            if not self.running:
                break

            # Sync system time from RTC
            self.sync_from_rtc()

    def stop(self):
        """Stop auto-sync"""
        self.running = False
        self.stop_event.set()

        if self.sync_thread:
            self.sync_thread.join(timeout=2)

        logging.info("RTC auto-sync stopped")

    def get_status(self) -> dict:
        """Get RTC status"""
        if not self.enabled:
            return {'enabled': False, 'available': False}

        try:
            result = subprocess.run(
                ['sudo', 'hwclock', '-r'],
                capture_output=True,
                text=True,
                timeout=5
            )

            available = result.returncode == 0
            rtc_time = result.stdout.strip() if available else None

            return {
                'enabled': True,
                'available': available,
                'rtc_time': rtc_time,
                'system_time': datetime.now().isoformat()
            }

        except Exception as e:
            logging.error(f"Error getting RTC status: {e}")
            return {'enabled': True, 'available': False, 'error': str(e)}
