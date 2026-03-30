# https://api.met.no/weatherapi/locationforecast/2.0/compact?altitude=353&lat=xx.xx&lon=yy.yy

import os
import logging
import requests
from datetime import datetime, timedelta, timezone
import utils

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)  # Parent directory (project root)

CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")

weatherLogger = logging.getLogger(__name__)
weatherLogger.setLevel(logging.INFO)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')


class WeatherServiceMetNo:
    """Service for fetching weather data from met.no API."""
    
    def __init__(self, config_filename=None, weather_data_filename=None):
        """Initialize the weather service.
        
        Args:
            config_filename: Path to config JSON file
            weather_data_filename: Path to output weather data JSON file
        """
        self.config_filename = config_filename or os.path.join(CONFIG_DIR, "config.json")
        self.weather_data_filename = weather_data_filename or os.path.join(DATA_DIR, "weather_data.json")
    
    def get_weather_data(self):
        """Gets weather data from met.no API. Result: weather_data.json file."""
        # Reload config to get latest location data
        config = utils.read_json(self.config_filename)
        
        params = {
            'altitude': config['location']['altitude'],
            'lat': round(config['location']['latitude'], 4),
            'lon': round(config['location']['longitude'], 4)
        }

        try:
            response = requests.get(
                "https://api.met.no/weatherapi/locationforecast/2.0/complete",
                params=params,
                headers={"User-Agent": "wgmv-weather/1.0"},
                timeout=30
            )

            weatherLogger.debug("%d %s", response.status_code, response.text)
            response.raise_for_status()
            weather_data = response.json()
            utils.write_json(weather_data, self.weather_data_filename)
        except requests.exceptions.HTTPError as e:
            weatherLogger.warning("get_weather_data() HTTPError")
            weatherLogger.warning("%d %s", e.response.status_code, e.response.text)
        except requests.exceptions.RequestException:
            weatherLogger.error("get_weather_data() RequestException:", exc_info=1)


class AirQualityServiceWAQI:
    """Service for fetching air quality data from WAQI API."""
    
    def __init__(self, config_filename=None, aqi_data_filename=None):
        """Initialize the air quality service.
        
        Args:
            config_filename: Path to config JSON file
            aqi_data_filename: Path to output air quality data JSON file
        """
        self.config_filename = config_filename or os.path.join(CONFIG_DIR, "config.json")
        self.aqi_data_filename = aqi_data_filename or os.path.join(DATA_DIR, "aqi_data.json")
    
    def get_aqi_data(self):
        """Gets air quality data from WAQI API. Result: aqi_data.json file.
        
        Requires 'waqi_token' in config.json.
        Get your token at: https://aqicn.org/data-platform/token/
        """
        # Reload config to get latest location data and token
        config = utils.read_json(self.config_filename)
        
        if 'waqi_token' not in config:
            weatherLogger.error("WAQI token not found in config.json. Get one at: https://aqicn.org/data-platform/token/")
            return
        
        lat = round(config['location']['latitude'], 4)
        lon = round(config['location']['longitude'], 4)
        token = config['waqi_token']
        
        # Use geo-localized feed endpoint
        url = f"https://api.waqi.info/feed/geo:{lat};{lon}/"
        params = {'token': token}

        try:
            response = requests.get(
                url,
                params=params,
                timeout=30
            )

            weatherLogger.debug("%d %s", response.status_code, response.text)
            response.raise_for_status()
            aqi_data = response.json()
            
            if aqi_data.get('status') == 'ok':
                utils.write_json(aqi_data, self.aqi_data_filename)
                weatherLogger.info("Air quality data retrieved successfully. AQI: %s", 
                                 aqi_data.get('data', {}).get('aqi', 'N/A'))
            else:
                weatherLogger.warning("WAQI API returned status: %s", aqi_data.get('status'))
                
        except requests.exceptions.HTTPError as e:
            weatherLogger.warning("get_aqi_data() HTTPError")
            weatherLogger.warning("%d %s", e.response.status_code, e.response.text)
        except requests.exceptions.RequestException:
            weatherLogger.error("get_aqi_data() RequestException:", exc_info=1)


class SunriseServiceMetNo:
    """Service for fetching sunrise/sunset data from met.no Sunrise API v3."""

    def __init__(self, config_filename=None, sunrise_data_filename=None):
        self.config_filename = config_filename or os.path.join(CONFIG_DIR, "config.json")
        self.sunrise_data_filename = sunrise_data_filename or os.path.join(DATA_DIR, "sunrise_data.json")

    def get_sunrise_data(self, debug=False):
        """Fetches sunrise/sunset times for today and tomorrow (UTC). Result: sunrise_data.json."""
        config = utils.read_json(self.config_filename)
        lat = round(config['location']['latitude'], 4)
        lon = round(config['location']['longitude'], 4)

        today = datetime.now(timezone.utc).date()
        dates = [today, today + timedelta(days=1)]
        results = {}

        for date in dates:
            date_str = date.isoformat()
            # Build URL manually to avoid '+' being percent-encoded as %2B which some servers reject
            url = (
                f"https://api.met.no/weatherapi/sunrise/3.0/sun"
                f"?lat={lat}&lon={lon}&date={date_str}&offset=+00:00"
            )
            try:
                response = requests.get(
                    url,
                    headers={"User-Agent": "wgmv-weather/1.0"},
                    timeout=30
                )
                if debug:
                    weatherLogger.info("GET %s  →  %d", response.url, response.status_code)
                    weatherLogger.info("Response body: %s", response.text[:500])
                response.raise_for_status()
                data = response.json()
                if debug:
                    weatherLogger.info("Parsed JSON keys at root: %s", list(data.keys()))
                    weatherLogger.info("properties keys: %s", list(data.get('properties', {}).keys()))
                props = data.get('properties', {})
                sunrise_iso = props.get('sunrise', {}).get('time', '')
                sunset_iso = props.get('sunset', {}).get('time', '')
                # Parse ISO 8601 and store as HH:MM UTC strings
                sunrise_utc = datetime.fromisoformat(sunrise_iso).strftime('%H:%M') if sunrise_iso else None
                sunset_utc = datetime.fromisoformat(sunset_iso).strftime('%H:%M') if sunset_iso else None
                results[date_str] = {'sunrise': sunrise_utc, 'sunset': sunset_utc}
                weatherLogger.info("Sunrise data for %s: sunrise=%s sunset=%s", date_str, sunrise_utc, sunset_utc)
            except requests.exceptions.HTTPError as e:
                weatherLogger.warning("get_sunrise_data() HTTPError for %s: %d %s",
                                      date_str, e.response.status_code, e.response.text)
            except requests.exceptions.RequestException:
                weatherLogger.error("get_sunrise_data() RequestException for %s:", date_str, exc_info=1)
            except (KeyError, ValueError) as e:
                weatherLogger.error("get_sunrise_data() failed to parse response for %s: %s", date_str, e)

        if results:
            utils.write_json(results, self.sunrise_data_filename)
        else:
            weatherLogger.warning("get_sunrise_data() produced no results — sunrise_data.json not written")

    @staticmethod
    def calculate_daylight_minutes(sunrise_hhmm, sunset_hhmm):
        """Returns the number of daylight minutes between sunrise and sunset (UTC HH:MM strings)."""
        fmt = '%H:%M'
        rise = datetime.strptime(sunrise_hhmm, fmt)
        sett = datetime.strptime(sunset_hhmm, fmt)
        return int((sett - rise).total_seconds() / 60)


if __name__ == '__main__':
    weather_service = WeatherServiceMetNo()
    weather_service.get_weather_data()

    aqi_service = AirQualityServiceWAQI()
    aqi_service.get_aqi_data()

    sunrise_service = SunriseServiceMetNo()
    sunrise_service.get_sunrise_data(debug=True)