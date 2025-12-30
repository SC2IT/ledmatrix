"""
OpenWeatherMap API client for weather data
"""

import logging
import time
import json
import requests
from typing import Optional, Callable, Dict
from datetime import datetime
from threading import Thread, Event, Lock


class OWMClient:
    """OpenWeatherMap API client with automatic updates and caching"""

    def __init__(self, config, on_weather_callback: Optional[Callable] = None):
        """
        Initialize OpenWeatherMap client

        Args:
            config: Config object with OWM settings
            on_weather_callback: Function to call when weather updates
        """
        self.config = config
        self.on_weather_callback = on_weather_callback

        # API settings
        self.api_key = config.data.get('openweathermap', {}).get('api_key')
        self.lat = config.data.get('openweathermap', {}).get('latitude')
        self.lon = config.data.get('openweathermap', {}).get('longitude')
        self.update_interval = config.data.get('openweathermap', {}).get('update_interval', 300)  # 5 minutes default

        if not self.api_key:
            raise ValueError("OpenWeatherMap API key not configured")
        if self.lat is None or self.lon is None:
            raise ValueError("Latitude and longitude not configured")

        # Data cache
        self.weather_data = None
        self.forecast_hourly = {}  # Key: hours ahead (6, 12)
        self.forecast_daily = {}   # Key: days ahead (1, 2)
        self.last_update = 0
        self.data_lock = Lock()

        # Update thread
        self.running = False
        self.update_thread = None
        self.stop_event = Event()

        logging.info(f"OWM Client initialized for lat={self.lat}, lon={self.lon}")

    def _map_owm_condition(self, owm_main: str, condition_id: int) -> str:
        """
        Map OpenWeatherMap condition codes to icon-compatible format

        OWM Codes: https://openweathermap.org/weather-conditions

        Args:
            owm_main: Main weather category (Clear, Clouds, Rain, etc.)
            condition_id: Detailed condition ID (800, 801, 500, etc.)

        Returns:
            Icon-compatible condition string
        """
        # Thunderstorm (200-232)
        if 200 <= condition_id < 300:
            return "Thunderstorms"

        # Drizzle (300-321)
        elif 300 <= condition_id < 400:
            return "Drizzle"

        # Rain (500-531)
        elif 500 <= condition_id < 600:
            if condition_id == 500:
                return "LightRain"
            elif condition_id in [501, 502, 503, 504]:
                return "Rain"
            elif condition_id >= 520:
                return "HeavyRain"
            else:
                return "Rain"

        # Snow (600-622)
        elif 600 <= condition_id < 700:
            if condition_id == 600:
                return "LightSnow"
            elif condition_id == 601:
                return "Snow"
            elif condition_id == 602:
                return "HeavySnow"
            elif condition_id == 611:
                return "IcePellets"  # Sleet
            elif condition_id == 612:
                return "LightFreezingRain"  # Light shower sleet
            elif condition_id == 613:
                return "FreezingRain"  # Shower sleet
            elif condition_id == 615:
                return "LightSnow"  # Light rain and snow
            elif condition_id == 616:
                return "Snow"  # Rain and snow
            elif condition_id == 620:
                return "Flurries"  # Light shower snow
            elif condition_id == 621:
                return "Snow"  # Shower snow
            elif condition_id == 622:
                return "HeavySnow"  # Heavy shower snow
            else:
                return "Snow"

        # Atmosphere (701-781)
        elif 700 <= condition_id < 800:
            if condition_id in [701, 711, 721]:
                return "LightFog"  # Mist, smoke, haze
            elif condition_id in [731, 741, 751, 761]:
                return "Fog"  # Dust, fog, sand, dust
            elif condition_id == 762:
                return "Fog"  # Volcanic ash
            elif condition_id == 771:
                return "Fog"  # Squalls
            elif condition_id == 781:
                return "Thunderstorms"  # Tornado (use thunderstorm icon)
            else:
                return "Fog"

        # Clear (800)
        elif condition_id == 800:
            return "Clear"

        # Clouds (801-804)
        elif 801 <= condition_id <= 804:
            if condition_id == 801:
                return "MostlyClear"  # Few clouds (11-25%)
            elif condition_id == 802:
                return "PartlyCloudy"  # Scattered clouds (25-50%)
            elif condition_id == 803:
                return "MostlyCloudy"  # Broken clouds (51-84%)
            elif condition_id == 804:
                return "Cloudy"  # Overcast (85-100%)

        # Default fallback
        return "Clear"

    def start(self):
        """Start automatic weather updates"""
        if self.running:
            return

        self.running = True
        self.stop_event.clear()

        # Initial fetch
        self._fetch_weather()

        # Start update thread
        self.update_thread = Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

        logging.info("OWM Client started")

    def stop(self):
        """Stop weather updates"""
        self.running = False
        self.stop_event.set()

        if self.update_thread:
            self.update_thread.join(timeout=5)

        logging.info("OWM Client stopped")

    def _update_loop(self):
        """Background thread for periodic weather updates"""
        while self.running and not self.stop_event.is_set():
            now = time.time()
            time_since_update = now - self.last_update

            if time_since_update >= self.update_interval:
                self._fetch_weather()

            # Sleep in small intervals to allow quick shutdown
            self.stop_event.wait(timeout=10)

    def _fetch_weather(self):
        """Fetch weather data from OpenWeatherMap API"""
        try:
            # Fetch current weather
            current_url = (
                f"https://api.openweathermap.org/data/2.5/weather?"
                f"lat={self.lat}&lon={self.lon}&appid={self.api_key}&units=imperial"
            )

            logging.debug(f"Fetching current weather from OWM")
            current_response = requests.get(current_url, timeout=10)
            current_response.raise_for_status()
            current_data = current_response.json()

            # Fetch 5-day forecast (3-hour intervals)
            forecast_url = (
                f"https://api.openweathermap.org/data/2.5/forecast?"
                f"lat={self.lat}&lon={self.lon}&appid={self.api_key}&units=imperial"
            )

            logging.debug(f"Fetching forecast from OWM")
            forecast_response = requests.get(forecast_url, timeout=10)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()

            # Process data
            with self.data_lock:
                self._process_current_weather(current_data)
                self._process_forecast(forecast_data)
                self.last_update = time.time()

            logging.info(f"Weather updated from OWM: {self.weather_data.get('temp')}°F, {self.weather_data.get('condition')}")

            # Trigger callback
            if self.on_weather_callback and self.weather_data:
                self.on_weather_callback(self.weather_data)

        except requests.exceptions.RequestException as e:
            logging.error(f"OWM API request failed: {e}")
        except Exception as e:
            logging.error(f"Error fetching weather from OWM: {e}", exc_info=True)

    def _process_current_weather(self, data: dict):
        """Process current weather data from OWM"""
        try:
            main = data.get('main', {})
            weather = data.get('weather', [{}])[0]
            wind = data.get('wind', {})
            sys_data = data.get('sys', {})

            # Extract values
            temp_f = round(main.get('temp', 0))
            feels_f = round(main.get('feels_like', temp_f))
            humidity = round(main.get('humidity', 0))
            pressure_hpa = main.get('pressure', 1013.25)
            pressure_inhg = round(pressure_hpa * 0.02953, 2)

            wind_speed_ms = wind.get('speed', 0)
            wind_mph = round(wind_speed_ms * 2.237)
            wind_deg = wind.get('deg', 0)

            # Map OpenWeatherMap condition codes to display icon format
            owm_condition = weather.get('main', 'Clear')
            condition_id = weather.get('id', 800)
            condition = self._map_owm_condition(owm_condition, condition_id)

            # Calculate wind direction
            dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            wind_dir_str = dirs[round(wind_deg / 45) % 8]

            # Determine day/night from sunrise/sunset
            sunrise = sys_data.get('sunrise', 0)
            sunset = sys_data.get('sunset', 0)
            now = time.time()
            is_night = now < sunrise or now > sunset

            # Temperature color
            def get_temp_color(t):
                if t <= 32:
                    return 4  # Blue
                if t >= 100:
                    return 2  # Red
                progress = (t - 32) / 68.0
                if progress < 0.4:
                    return 7  # Cyan
                if progress <= 0.603:
                    return 3  # Green
                if progress < 0.8:
                    return 5  # Yellow
                return 8  # Orange

            # Precipitation (from rain/snow data if available)
            rain_1h = data.get('rain', {}).get('1h', 0)
            snow_1h = data.get('snow', {}).get('1h', 0)
            precip_chance = 0
            if rain_1h > 0 or snow_1h > 0:
                precip_chance = 100  # OWM doesn't provide % chance, only actual precip

            # Store weather data
            self.weather_data = {
                'temp': temp_f,
                'temp_color': get_temp_color(temp_f),
                'feels_like': feels_f,
                'feels_like_color': get_temp_color(feels_f),
                'wind_speed': wind_mph,
                'wind_dir': wind_dir_str,
                'humidity': humidity,
                'pressure': pressure_inhg,
                'pressure_trend': 'steady',  # OWM doesn't provide trend
                'is_night': is_night,
                'condition': condition,
                'precip_chance': precip_chance
            }

            # Update day/night mode
            was_night = self.config._is_night
            self.config.set_night_mode(is_night)

            if was_night != is_night:
                logging.info(f"Night mode changed: {was_night} -> {is_night}")

        except Exception as e:
            logging.error(f"Error processing current weather: {e}", exc_info=True)

    def _process_forecast(self, data: dict):
        """Process forecast data from OWM (5-day, 3-hour intervals)"""
        try:
            forecast_list = data.get('list', [])

            if not forecast_list:
                return

            # Extract hourly forecasts (closest to +6h and +12h)
            now = time.time()
            target_times = {
                6: now + (6 * 3600),
                12: now + (12 * 3600)
            }

            for hours, target_time in target_times.items():
                # Find closest forecast to target time
                closest = min(forecast_list, key=lambda x: abs(x['dt'] - target_time))

                main = closest.get('main', {})
                weather = closest.get('weather', [{}])[0]

                temp_f = round(main.get('temp', 0))
                owm_condition = weather.get('main', 'Clear')
                condition_id = weather.get('id', 800)
                condition = self._map_owm_condition(owm_condition, condition_id)
                precip_prob = closest.get('pop', 0) * 100  # Probability of precipitation

                self.forecast_hourly[hours] = {
                    'temp': temp_f,
                    'condition': condition,
                    'time': datetime.fromtimestamp(closest['dt']).strftime('%H:%M'),
                    'precip_chance': round(precip_prob)
                }

            # Extract daily forecasts (today + next 2 days)
            # Group by day and calculate high/low
            from collections import defaultdict
            daily_temps = defaultdict(lambda: {'temps': [], 'conditions': [], 'precip': []})

            for item in forecast_list:
                dt = datetime.fromtimestamp(item['dt'])
                day_offset = (dt.date() - datetime.now().date()).days

                if 0 <= day_offset <= 2:  # Today, tomorrow, and day after
                    daily_temps[day_offset]['temps'].append(item['main']['temp'])
                    # Store mapped condition
                    owm_cond = item['weather'][0]['main']
                    cond_id = item['weather'][0]['id']
                    mapped_cond = self._map_owm_condition(owm_cond, cond_id)
                    daily_temps[day_offset]['conditions'].append(mapped_cond)
                    daily_temps[day_offset]['precip'].append(item.get('pop', 0) * 100)

            # Calculate daily summary
            for day, data_dict in daily_temps.items():
                if data_dict['temps']:
                    # Most common mapped condition
                    if data_dict['conditions']:
                        most_common_condition = max(set(data_dict['conditions']), key=data_dict['conditions'].count)
                    else:
                        most_common_condition = 'Clear'
                        logging.warning(f"No conditions found for day {day}, defaulting to Clear")

                    logging.debug(f"Day {day} forecast: temps={data_dict['temps'][:3]}..., conditions={data_dict['conditions'][:3]}..., most_common={most_common_condition}")

                    self.forecast_daily[day] = {
                        'temp_max': round(max(data_dict['temps'])),
                        'temp_min': round(min(data_dict['temps'])),
                        'condition': most_common_condition,
                        'date': '',
                        'precip_chance': round(max(data_dict['precip']))  # Max chance during day
                    }

            logging.debug(f"Forecast processed: hourly={list(self.forecast_hourly.keys())}, daily={list(self.forecast_daily.keys())}")

        except Exception as e:
            logging.error(f"Error processing forecast: {e}", exc_info=True)

    def get_weather_data(self) -> Optional[Dict]:
        """Get current weather data"""
        with self.data_lock:
            return self.weather_data

    def get_hourly_forecasts(self) -> Dict:
        """Get hourly forecast data"""
        with self.data_lock:
            return self.forecast_hourly.copy()

    def get_daily_forecasts(self) -> Dict:
        """Get daily forecast data"""
        with self.data_lock:
            return self.forecast_daily.copy()

    def get_data_age(self) -> float:
        """Get age of cached data in seconds"""
        if self.last_update == 0:
            return float('inf')
        return time.time() - self.last_update

    def is_data_stale(self, max_age: int = 600) -> bool:
        """Check if data is stale (default: 10 minutes)"""
        return self.get_data_age() > max_age
