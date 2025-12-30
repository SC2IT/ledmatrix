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
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class WeatherData:
    """Current weather conditions with full Python type safety"""
    temp: int
    temp_color: int
    feels_like: int
    feels_like_color: int
    wind_speed: int
    wind_gust: int
    wind_dir: str
    humidity: int
    pressure: float
    pressure_trend: str
    is_night: bool
    condition: str
    precip_chance: int
    uvi: float
    dew_point: int
    clouds: int
    visibility: int

    def to_dict(self) -> Dict:
        """Convert to dict for backwards compatibility"""
        return {
            'temp': self.temp,
            'temp_color': self.temp_color,
            'feels_like': self.feels_like,
            'feels_like_color': self.feels_like_color,
            'wind_speed': self.wind_speed,
            'wind_gust': self.wind_gust,
            'wind_dir': self.wind_dir,
            'humidity': self.humidity,
            'pressure': self.pressure,
            'pressure_trend': self.pressure_trend,
            'is_night': self.is_night,
            'condition': self.condition,
            'precip_chance': self.precip_chance,
            'uvi': self.uvi,
            'dew_point': self.dew_point,
            'clouds': self.clouds,
            'visibility': self.visibility
        }


@dataclass
class HourlyForecast:
    """Hourly forecast data with type safety"""
    temp: int
    condition: str
    time: str
    precip_chance: int
    wind_speed: int
    wind_gust: int
    humidity: int
    uvi: float

    def to_dict(self) -> Dict:
        """Convert to dict for backwards compatibility"""
        return {
            'temp': self.temp,
            'condition': self.condition,
            'time': self.time,
            'precip_chance': self.precip_chance,
            'wind_speed': self.wind_speed,
            'wind_gust': self.wind_gust,
            'humidity': self.humidity,
            'uvi': self.uvi
        }


@dataclass
class DailyForecast:
    """Daily forecast data with type safety"""
    temp_max: int
    temp_min: int
    temp_day: int
    temp_night: int
    temp_eve: int
    temp_morn: int
    condition: str
    date: str
    precip_chance: int
    summary: str
    humidity: int
    wind_speed: int
    wind_gust: int
    uvi: float
    sunrise: int
    sunset: int

    def to_dict(self) -> Dict:
        """Convert to dict for backwards compatibility"""
        return {
            'temp_max': self.temp_max,
            'temp_min': self.temp_min,
            'temp_day': self.temp_day,
            'temp_night': self.temp_night,
            'temp_eve': self.temp_eve,
            'temp_morn': self.temp_morn,
            'condition': self.condition,
            'date': self.date,
            'precip_chance': self.precip_chance,
            'summary': self.summary,
            'humidity': self.humidity,
            'wind_speed': self.wind_speed,
            'wind_gust': self.wind_gust,
            'uvi': self.uvi,
            'sunrise': self.sunrise,
            'sunset': self.sunset
        }


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

    @lru_cache(maxsize=256)
    def _map_owm_condition(self, owm_main: str, condition_id: int) -> str:
        """
        Map OpenWeatherMap condition codes to icon-compatible format.

        Cached to avoid repeated string processing for same condition codes.
        With ~100 possible OWM condition codes, 256 cache entries is sufficient.

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
        """Fetch weather data from OpenWeatherMap One Call API 3.0"""
        try:
            # Fetch all data with One Call API 3.0 (1 call instead of 2)
            onecall_url = (
                f"https://api.openweathermap.org/data/3.0/onecall?"
                f"lat={self.lat}&lon={self.lon}&appid={self.api_key}&units=imperial"
            )

            logging.debug(f"Fetching weather from OWM One Call API 3.0")
            response = requests.get(onecall_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Process data
            with self.data_lock:
                self._process_current_weather(data.get('current', {}), data.get('timezone_offset', 0))
                self._process_forecast(data.get('hourly', []), data.get('daily', []))
                self.last_update = time.time()

            logging.info(f"Weather updated from OWM: {self.weather_data.get('temp')}°F, {self.weather_data.get('condition')}")

            # Trigger callback
            if self.on_weather_callback and self.weather_data:
                self.on_weather_callback(self.weather_data)

        except requests.exceptions.RequestException as e:
            logging.error(f"OWM API request failed: {e}")
        except Exception as e:
            logging.error(f"Error fetching weather from OWM: {e}", exc_info=True)

    def _process_current_weather(self, data: dict, timezone_offset: int = 0):
        """Process current weather data from OWM One Call API 3.0"""
        try:
            # One Call API 3.0 has flatter structure (no 'main' nesting)
            weather = data.get('weather', [{}])[0]

            # Extract values (imperial units already applied)
            temp_f = round(data.get('temp', 0))
            feels_f = round(data.get('feels_like', temp_f))
            humidity = round(data.get('humidity', 0))
            pressure_hpa = data.get('pressure', 1013.25)
            pressure_inhg = round(pressure_hpa * 0.02953, 2)

            wind_speed_mph = round(data.get('wind_speed', 0))  # Already in MPH with imperial units
            wind_deg = data.get('wind_deg', 0)
            wind_gust_mph = round(data.get('wind_gust', 0))  # NEW in One Call API

            # NEW fields in One Call API 3.0
            uvi = round(data.get('uvi', 0), 1)  # UV Index
            dew_point_f = round(data.get('dew_point', 0))
            clouds = data.get('clouds', 0)  # Cloud coverage %
            visibility = data.get('visibility', 10000)  # meters

            # Map OpenWeatherMap condition codes to display icon format
            owm_condition = weather.get('main', 'Clear')
            condition_id = weather.get('id', 800)
            condition = self._map_owm_condition(owm_condition, condition_id)

            # Calculate wind direction
            dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            wind_dir_str = dirs[round(wind_deg / 45) % 8]

            # Determine day/night from sunrise/sunset (in current object for One Call API)
            sunrise = data.get('sunrise', 0)
            sunset = data.get('sunset', 0)
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
            rain_1h = data.get('rain', {}).get('1h', 0) if isinstance(data.get('rain'), dict) else 0
            snow_1h = data.get('snow', {}).get('1h', 0) if isinstance(data.get('snow'), dict) else 0
            precip_chance = 0
            if rain_1h > 0 or snow_1h > 0:
                precip_chance = 100  # Current conditions don't have pop, only actual precip

            # Store weather data as typed dataclass (convert to dict for backwards compatibility)
            weather_obj = WeatherData(
                temp=temp_f,
                temp_color=get_temp_color(temp_f),
                feels_like=feels_f,
                feels_like_color=get_temp_color(feels_f),
                wind_speed=wind_speed_mph,
                wind_gust=wind_gust_mph,
                wind_dir=wind_dir_str,
                humidity=humidity,
                pressure=pressure_inhg,
                pressure_trend='steady',  # OWM doesn't provide trend
                is_night=is_night,
                condition=condition,
                precip_chance=precip_chance,
                uvi=uvi,
                dew_point=dew_point_f,
                clouds=clouds,
                visibility=visibility
            )
            # Convert to dict for backwards compatibility with existing display code
            self.weather_data = weather_obj.to_dict()

            # Update day/night mode
            was_night = self.config._is_night
            self.config.set_night_mode(is_night)

            if was_night != is_night:
                logging.info(f"Night mode changed: {was_night} -> {is_night}")

        except Exception as e:
            logging.error(f"Error processing current weather: {e}", exc_info=True)

    def _process_forecast(self, hourly_list: list, daily_list: list):
        """Process forecast data from OWM One Call API 3.0"""
        try:
            # Process hourly forecasts (48 hours available, use +6h and +12h)
            if hourly_list and len(hourly_list) >= 12:
                for hours in [6, 12]:
                    if hours < len(hourly_list):
                        hour_data = hourly_list[hours]
                        weather = hour_data.get('weather', [{}])[0]

                        temp_f = round(hour_data.get('temp', 0))
                        owm_condition = weather.get('main', 'Clear')
                        condition_id = weather.get('id', 800)
                        condition = self._map_owm_condition(owm_condition, condition_id)
                        precip_prob = hour_data.get('pop', 0) * 100  # Probability of precipitation

                        # Create typed dataclass (convert to dict for backwards compatibility)
                        hourly_obj = HourlyForecast(
                            temp=temp_f,
                            condition=condition,
                            time=datetime.fromtimestamp(hour_data['dt']).strftime('%H:%M'),
                            precip_chance=round(precip_prob),
                            wind_speed=round(hour_data.get('wind_speed', 0)),
                            wind_gust=round(hour_data.get('wind_gust', 0)),
                            humidity=round(hour_data.get('humidity', 0)),
                            uvi=round(hour_data.get('uvi', 0), 1)
                        )
                        self.forecast_hourly[hours] = hourly_obj.to_dict()

            # Process daily forecasts (8 days available, use days 0-2)
            if daily_list:
                for day_offset in range(min(3, len(daily_list))):
                    day_data = daily_list[day_offset]
                    weather = day_data.get('weather', [{}])[0]
                    temp_obj = day_data.get('temp', {})

                    # Map condition
                    owm_condition = weather.get('main', 'Clear')
                    condition_id = weather.get('id', 800)
                    condition = self._map_owm_condition(owm_condition, condition_id)

                    # Extract temperatures (One Call API provides detailed temp breakdown)
                    temp_max = round(temp_obj.get('max', 0))
                    temp_min = round(temp_obj.get('min', 0))
                    temp_day = round(temp_obj.get('day', 0))
                    temp_night = round(temp_obj.get('night', 0))
                    temp_eve = round(temp_obj.get('eve', 0))
                    temp_morn = round(temp_obj.get('morn', 0))

                    # Precipitation probability
                    precip_prob = day_data.get('pop', 0) * 100

                    # Summary (One Call API provides this!)
                    summary = day_data.get('summary', '')

                    # Create typed dataclass (convert to dict for backwards compatibility)
                    daily_obj = DailyForecast(
                        temp_max=temp_max,
                        temp_min=temp_min,
                        temp_day=temp_day,
                        temp_night=temp_night,
                        temp_eve=temp_eve,
                        temp_morn=temp_morn,
                        condition=condition,
                        date=datetime.fromtimestamp(day_data['dt']).strftime('%a %m/%d'),
                        precip_chance=round(precip_prob),
                        summary=summary,
                        humidity=round(day_data.get('humidity', 0)),
                        wind_speed=round(day_data.get('wind_speed', 0)),
                        wind_gust=round(day_data.get('wind_gust', 0)),
                        uvi=round(day_data.get('uvi', 0), 1),
                        sunrise=day_data.get('sunrise', 0),
                        sunset=day_data.get('sunset', 0)
                    )
                    self.forecast_daily[day_offset] = daily_obj.to_dict()

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
