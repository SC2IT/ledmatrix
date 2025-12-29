"""
Adafruit IO client with MQTT and REST API support
"""

import logging
import time
import requests
from typing import Optional, Callable
from threading import Thread, Event
import paho.mqtt.client as mqtt


class AIOClient:
    """Adafruit IO client with MQTT and REST fallback"""

    def __init__(self, config, on_message_callback: Optional[Callable] = None):
        """
        Initialize Adafruit IO client

        Args:
            config: Config object
            on_message_callback: Function to call when message received (msg_dict)
        """
        self.config = config
        self.on_message_callback = on_message_callback

        # MQTT state
        self.mqtt_client = None
        self.mqtt_connected = False
        self.mqtt_enabled = config.mqtt_enabled

        # REST state
        self.rest_enabled = config.rest_enabled
        self.last_rest_poll = 0
        self.last_command = None

        # Control
        self.running = False
        self.stop_event = Event()

        # Initialize MQTT if enabled
        if self.mqtt_enabled:
            self._init_mqtt()

    def _init_mqtt(self):
        """Initialize MQTT client"""
        try:
            self.mqtt_client = mqtt.Client(protocol=mqtt.MQTTv311)

            # Set credentials
            self.mqtt_client.username_pw_set(
                self.config.aio_username,
                self.config.aio_key
            )

            # Set callbacks
            self.mqtt_client.on_connect = self._on_connect
            self.mqtt_client.on_disconnect = self._on_disconnect
            self.mqtt_client.on_message = self._on_mqtt_message

            # Connect
            broker = self.config.data['aio'].get('mqtt', {}).get('broker', 'io.adafruit.com')
            port = self.config.data['aio'].get('mqtt', {}).get('port', 1883)
            keepalive = self.config.data['aio'].get('mqtt', {}).get('keepalive', 60)

            logging.info(f"Connecting to MQTT broker: {broker}:{port}")
            self.mqtt_client.connect(broker, port, keepalive)

            # Start loop in background thread
            self.mqtt_client.loop_start()

        except Exception as e:
            logging.error(f"MQTT initialization failed: {e}")
            self.mqtt_enabled = False

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.mqtt_connected = True
            logging.info("Connected to Adafruit IO MQTT")

            # Subscribe to command feed
            feed_topic = f"{self.config.aio_username}/feeds/{self.config.aio_feed}"
            client.subscribe(feed_topic)
            logging.info(f"Subscribed to {feed_topic}")

        else:
            self.mqtt_connected = False
            logging.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.mqtt_connected = False
        if rc != 0:
            logging.warning(f"Unexpected MQTT disconnection (rc={rc}), will auto-reconnect")
        else:
            logging.info("MQTT disconnected")

    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT message callback"""
        try:
            payload = msg.payload.decode('utf-8')
            logging.debug(f"MQTT message received: {payload}")

            # Parse message
            if self.on_message_callback:
                self.on_message_callback({'value': payload, 'source': 'mqtt'})

        except Exception as e:
            logging.error(f"Error processing MQTT message: {e}")

    def poll_rest_api(self) -> Optional[dict]:
        """
        Poll Adafruit IO REST API for latest command

        Returns:
            Dictionary with 'value' key, or None if no new data
        """
        if not self.rest_enabled:
            return None

        # Check poll interval
        now = time.time()
        if now - self.last_rest_poll < self.config.rest_poll_interval:
            return None

        self.last_rest_poll = now

        try:
            url = f"https://io.adafruit.com/api/v2/{self.config.aio_username}/feeds/{self.config.aio_feed}/data/last"
            headers = {"X-AIO-KEY": self.config.aio_key}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                command = data.get('value', '')

                # Only return if different from last command
                if command != self.last_command:
                    self.last_command = command
                    logging.debug(f"REST API: New command '{command}'")
                    return {'value': command, 'source': 'rest'}
                else:
                    return None
            else:
                logging.warning(f"REST API returned status {response.status_code}")
                return None

        except Exception as e:
            logging.error(f"REST API poll error: {e}")
            return None

    def start(self):
        """Start the client"""
        self.running = True
        logging.info("AIO Client started")

    def stop(self):
        """Stop the client"""
        self.running = False
        self.stop_event.set()

        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

        logging.info("AIO Client stopped")

    def is_connected(self) -> bool:
        """Check if connected (MQTT or REST available)"""
        return self.mqtt_connected or self.rest_enabled

    def get_status(self) -> dict:
        """Get connection status"""
        return {
            'mqtt_enabled': self.mqtt_enabled,
            'mqtt_connected': self.mqtt_connected,
            'rest_enabled': self.rest_enabled,
            'connected': self.is_connected()
        }
