"""
Adafruit IO client with MQTT and REST API support
"""

import logging
import time
import json
import requests
from typing import Optional, Callable
from threading import Thread, Event
from datetime import datetime
import paho.mqtt.client as mqtt
from astral import LocationInfo
from astral.sun import sun


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


class WeatherClient:
    """Adafruit IO Weather client (MQTT subscription)"""

    def __init__(self, config, on_weather_callback: Optional[Callable] = None):
        """
        Initialize weather client

        Args:
            config: Config object
            on_weather_callback: Function to call with weather data
        """
        self.config = config
        self.on_weather_callback = on_weather_callback

        # MQTT state
        self.mqtt_client = None
        self.mqtt_connected = False
        self.weather_data = None

        # Initialize MQTT
        self._init_mqtt()

    def _init_mqtt(self):
        """Initialize MQTT client for weather"""
        try:
            self.mqtt_client = mqtt.Client(client_id=f"weather_{self.config.aio_username}", protocol=mqtt.MQTTv311)

            # Set credentials
            self.mqtt_client.username_pw_set(
                self.config.aio_username,
                self.config.aio_key
            )

            # Set callbacks
            self.mqtt_client.on_connect = self._on_connect
            self.mqtt_client.on_disconnect = self._on_disconnect
            self.mqtt_client.on_message = self._on_message

            # Connect
            broker = self.config.data['aio'].get('mqtt', {}).get('broker', 'io.adafruit.com')
            port = self.config.data['aio'].get('mqtt', {}).get('port', 1883)

            logging.info(f"Connecting to Weather MQTT: {broker}:{port}")
            self.mqtt_client.connect(broker, port, 60)

            # Start loop
            self.mqtt_client.loop_start()

        except Exception as e:
            logging.error(f"Weather MQTT initialization failed: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.mqtt_connected = True
            logging.info("Connected to Weather MQTT")

            # Subscribe to weather feed (integration path)
            location_id = self.config.weather_location_id
            weather_topic = f"{self.config.aio_username}/integration/weather/{location_id}/current"
            client.subscribe(weather_topic)
            logging.info(f"Subscribed to weather: {weather_topic}")

        else:
            self.mqtt_connected = False
            logging.error(f"Weather MQTT connection failed (rc={rc})")

    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.mqtt_connected = False
        if rc != 0:
            logging.warning(f"Weather MQTT disconnected (rc={rc}), will auto-reconnect")

    def _on_message(self, client, userdata, msg):
        """MQTT weather message callback"""
        try:
            payload = msg.payload.decode('utf-8')
            logging.debug(f"Weather MQTT received on {msg.topic}")

            # Parse JSON
            data = json.loads(payload)

            # Extract weather data directly from top level
            # Note: Adafruit IO weather integration sends data at top level, not nested in 'current'
            temp_c = data.get('temperature')
            if temp_c is None:
                logging.warning("Weather data missing temperature")
                return

            feels_c = data.get('temperatureApparent', temp_c)
            condition = data.get('conditionCode', 'Clear')
            wind_ms = data.get('windSpeed', 0)
            wind_dir = data.get('windDirection', 0)
            humidity = data.get('humidity', 0) * 100
            pressure_hpa = data.get('pressure', 1013.25)
            pressure_trend = data.get('pressureTrend', 'steady')

            # Calculate day/night based on sunrise/sunset
            metadata = data.get('metadata', {})
            latitude = metadata.get('latitude', 39.03)
            longitude = metadata.get('longitude', -94.68)

            # Calculate sunrise/sunset for location
            try:
                location = LocationInfo(latitude=latitude, longitude=longitude)
                s = sun(location.observer, date=datetime.now().date())
                now = datetime.now(s['sunrise'].tzinfo)  # Use same timezone as sun times
                is_night = now < s['sunrise'] or now > s['sunset']
                logging.debug(f"Sunrise: {s['sunrise'].strftime('%H:%M')}, Sunset: {s['sunset'].strftime('%H:%M')}, Now: {now.strftime('%H:%M')}, Night: {is_night}")
            except Exception as e:
                logging.warning(f"Could not calculate sunrise/sunset: {e}")
                # Fallback to weather data daylight field
                is_night = not data.get('daylight', True)

            # Convert to imperial
            temp_f = round(temp_c * 9 / 5 + 32)
            feels_f = round(feels_c * 9 / 5 + 32)
            wind_mph = round(wind_ms * 2.237)
            pressure_inhg = round(pressure_hpa * 0.02953, 2)

            # Wind direction
            dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            wind_dir_str = dirs[round(wind_dir / 45) % 8]

            # Temperature color
            def get_temp_color(t):
                if t <= 32:
                    return 4  # Blue
                if t >= 100:
                    return 2  # Red
                progress = (t - 32) / 68.0
                if progress < 0.4:
                    return 7  # Cyan
                if progress <= 0.603:  # Adjusted to include 73°F as green
                    return 3  # Green
                if progress < 0.8:
                    return 5  # Yellow
                return 8  # Orange

            # Store weather data
            self.weather_data = {
                'temp': temp_f,
                'temp_color': get_temp_color(temp_f),
                'feels_like': feels_f,
                'feels_like_color': get_temp_color(feels_f),
                'wind_speed': wind_mph,
                'wind_dir': wind_dir_str,
                'humidity': round(humidity),
                'pressure': pressure_inhg,
                'pressure_trend': pressure_trend,
                'is_night': is_night,
                'condition': condition
            }

            # Update day/night mode based on sunrise/sunset
            was_night = self.config._is_night
            self.config.set_night_mode(is_night)

            if was_night != is_night:
                logging.info(f"Night mode changed: {was_night} -> {is_night}")

            logging.info(f"Weather updated: {temp_f}°F, {condition}, Night={is_night}")

            # Call callback
            if self.on_weather_callback:
                self.on_weather_callback(self.weather_data)

        except Exception as e:
            logging.error(f"Error processing weather data: {e}")

    def get_weather_data(self) -> Optional[dict]:
        """Get latest weather data"""
        return self.weather_data

    def stop(self):
        """Stop weather client"""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        logging.info("Weather client stopped")
