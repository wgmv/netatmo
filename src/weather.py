# https://api.met.no/weatherapi/locationforecast/2.0/compact?altitude=353&lat=xx.xx&lon=yy.yy

import os
import logging
from datetime import datetime, timedelta
import requests
import utils

CONFIG_DIR = utils.CONFIG_DIR
DATA_DIR = utils.DATA_DIR

USER_AGENT = {"User-Agent": "wgmv-weather/1.0"}

weatherLogger = logging.getLogger(__name__)


def _load_config(config, config_filename):
    """Return the given config dict, or read it from disk if none was passed."""
    return config if config is not None else utils.read_json(config_filename)


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

    def get_weather_data(self, config=None):
        """Gets weather data from met.no API. Result: weather_data.json file.

        Args:
            config: Already loaded config dict (read from disk when omitted)
        """
        config = _load_config(config, self.config_filename)

        params = {
            'altitude': config['location']['altitude'],
            'lat': round(config['location']['latitude'], 4),
            'lon': round(config['location']['longitude'], 4)
        }

        try:
            response = requests.get(
                "https://api.met.no/weatherapi/locationforecast/2.0/complete",
                params=params,
                headers=USER_AGENT,
                timeout=30
            )

            weatherLogger.debug("%d %s", response.status_code, response.text)
            response.raise_for_status()
            utils.write_json(response.json(), self.weather_data_filename)
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

    def get_aqi_data(self, config=None):
        """Gets air quality data from WAQI API. Result: aqi_data.json file.

        Requires 'waqi_token' in config.json.
        Get your token at: https://aqicn.org/data-platform/token/
        """
        config = _load_config(config, self.config_filename)

        if 'waqi_token' not in config:
            weatherLogger.error("WAQI token not found in config.json. Get one at: https://aqicn.org/data-platform/token/")
            return

        lat = round(config['location']['latitude'], 4)
        lon = round(config['location']['longitude'], 4)

        # Use geo-localized feed endpoint
        url = f"https://api.waqi.info/feed/geo:{lat};{lon}/"

        try:
            response = requests.get(url, params={'token': config['waqi_token']}, timeout=30)

            # Do not log response.url / headers: the request URL contains the token
            weatherLogger.debug("WAQI %d", response.status_code)
            response.raise_for_status()
            aqi_data = response.json()

            if aqi_data.get('status') == 'ok':
                utils.write_json(aqi_data, self.aqi_data_filename)
                weatherLogger.info("Air quality data retrieved successfully. AQI: %s",
                                   aqi_data.get('data', {}).get('aqi', 'N/A'))
            else:
                weatherLogger.warning("WAQI API returned status: %s", aqi_data.get('status'))

        except requests.exceptions.HTTPError as e:
            weatherLogger.warning("get_aqi_data() HTTPError %d", e.response.status_code)
        except requests.exceptions.RequestException as e:
            # Not exc_info: the traceback message embeds the URL including the token
            weatherLogger.error("get_aqi_data() RequestException: %s", type(e).__name__)


class SunriseServiceMetNo:
    """Service for fetching sunrise/sunset data from met.no Sunrise API v3."""

    def __init__(self, config_filename=None, sunrise_data_filename=None):
        self.config_filename = config_filename or os.path.join(CONFIG_DIR, "config.json")
        self.sunrise_data_filename = sunrise_data_filename or os.path.join(DATA_DIR, "sunrise_data.json")
        self._cache = {}  # date_str -> {'sunrise': 'HH:MM', 'sunset': 'HH:MM'}

    def get_sunrise_data(self, config=None, debug=False):
        """Fetches sunrise/sunset times for today and tomorrow (local time). Result: sunrise_data.json.

        Dates that were already fetched successfully are served from an in-memory cache,
        so normally only one request per day is made.
        """
        config = _load_config(config, self.config_filename)
        lat = round(config['location']['latitude'], 4)
        lon = round(config['location']['longitude'], 4)

        # Use local date and offset so stored times match the local timezone (consistent with forecast data)
        local_now = datetime.now().astimezone()
        local_offset_raw = local_now.strftime('%z')  # e.g. '+0200'
        local_offset = f"{local_offset_raw[:3]}:{local_offset_raw[3:]}"  # e.g. '+02:00'
        today = local_now.date()
        wanted = [(today + timedelta(days=d)).isoformat() for d in (0, 1)]

        # Drop past dates, keep what we already have
        self._cache = {d: v for d, v in self._cache.items() if d in wanted}
        missing = [d for d in wanted if d not in self._cache]
        if not missing:
            weatherLogger.debug("Sunrise data up to date, no request needed")
            return

        for date_str in missing:
            # Build URL manually to avoid '+' being percent-encoded as %2B which some servers reject
            url = (
                f"https://api.met.no/weatherapi/sunrise/3.0/sun"
                f"?lat={lat}&lon={lon}&date={date_str}&offset={local_offset}"
            )
            try:
                response = requests.get(url, headers=USER_AGENT, timeout=30)
                if debug:
                    weatherLogger.info("GET %s  →  %d", response.url, response.status_code)
                    weatherLogger.info("Response body: %s", response.text[:500])
                response.raise_for_status()
                props = response.json().get('properties', {})
                sunrise_iso = props.get('sunrise', {}).get('time', '')
                sunset_iso = props.get('sunset', {}).get('time', '')
                # Parse ISO 8601 and store as local HH:MM strings
                sunrise_local = datetime.fromisoformat(sunrise_iso).strftime('%H:%M') if sunrise_iso else None
                sunset_local = datetime.fromisoformat(sunset_iso).strftime('%H:%M') if sunset_iso else None
                self._cache[date_str] = {'sunrise': sunrise_local, 'sunset': sunset_local}
                weatherLogger.info("Sunrise data for %s: sunrise=%s sunset=%s (offset %s)",
                                   date_str, sunrise_local, sunset_local, local_offset)
            except requests.exceptions.HTTPError as e:
                weatherLogger.warning("get_sunrise_data() HTTPError for %s: %d %s",
                                      date_str, e.response.status_code, e.response.text)
            except requests.exceptions.RequestException:
                weatherLogger.error("get_sunrise_data() RequestException for %s:", date_str, exc_info=1)
            except (KeyError, ValueError) as e:
                weatherLogger.error("get_sunrise_data() failed to parse response for %s: %s", date_str, e)

        if self._cache:
            utils.write_json(self._cache, self.sunrise_data_filename)
        else:
            weatherLogger.warning("get_sunrise_data() produced no results — sunrise_data.json not written")


if __name__ == '__main__':
    utils.setup_logging()
    WeatherServiceMetNo().get_weather_data()
    AirQualityServiceWAQI().get_aqi_data()
    SunriseServiceMetNo().get_sunrise_data(debug=True)
