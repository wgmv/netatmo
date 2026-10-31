#!/usr/bin/env python3
"""netatmo.py
NetAtmo weather station display
Periodically fetches weather station data and updates the display.
"""

import logging
import os
import sys
import time
from datetime import datetime

import requests

import display
import formatters
import utils
import weather

netatmoLogger = logging.getLogger(__name__)

# JSON file names
CONFIG_DIR = utils.CONFIG_DIR
DATA_DIR = utils.DATA_DIR
CONFIG_FILENAME = os.path.join(CONFIG_DIR, "config.json")
TOKEN_FILENAME = os.path.join(CONFIG_DIR, "token.json")
DATA_FILENAME = os.path.join(DATA_DIR, "data.json")

# Default values
CONFIG_DEFAULT = {
    "client_id": "xxxx",
    "client_secret": "xxxx",
    "device_id": "xxxx",
    "refresh_time": 600,
    "location": {
        "longitude": 0.0,
        "latitude": 0.0,
        "altitude": 0
    }
}
TOKEN_DEFAULT = {
    "access_token": "xxxx",
    "refresh_token": "xxxx"
}
REFRESH_TIME_DEFAULT = 600   # default 10 minutes
NIGHT_REFRESH_TIME = 1800    # 30 minutes during night hours
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 4
WEATHER_INTERVAL = 3600      # Fetch weather every 60 minutes


def _is_night():
    hour = datetime.now().hour
    return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


class NetatmoService:
    """Service for managing Netatmo weather station data."""
    
    def __init__(self):
        self.config = {}
        self.token = {}
        self.data = {}
        self.console_formatter = formatters.NetatmoConsoleFormatter()
        self.weather_service = weather.WeatherServiceMetNo()
        self.air_quality_service = weather.AirQualityServiceWAQI()
        self.sunrise_service = weather.SunriseServiceMetNo()
        self.last_weather_fetch = 0
        self.weather_interval = WEATHER_INTERVAL
        self.weather_display = None   # Created once in run() after config is loaded

    def get_new_token_info(self):
        """Instruct the user to authenticate on the dev portal and get a new token."""
        netatmoLogger.error('_______________________________________________________')
        netatmoLogger.error("Please generate a new access token, edit %s,", TOKEN_FILENAME)
        netatmoLogger.error("and try again.")
        netatmoLogger.error(' - Go to https://dev.netatmo.com/apps/, authenticate')
        netatmoLogger.error('   if necessary, and select your app.')
        netatmoLogger.error(' - Under "Token generator", select the "read_station"')
        netatmoLogger.error('   scope and click "Generate Token".')
        netatmoLogger.error(' - It takes a while, but you will get a page where you')
        netatmoLogger.error('   have to authorize your app to access to your data.')
        netatmoLogger.error(' - Click "Yes I accept".')
        netatmoLogger.error('   You now have a new Access Token and a new Refresh')
        netatmoLogger.error('   token.')
        netatmoLogger.error(' - Click on the access token. It will copy it to your')
        netatmoLogger.error('   clipboard. Paste it in your %s file in place', TOKEN_FILENAME)
        netatmoLogger.error('   of the access_token placeholder.')
        netatmoLogger.error(' - same thing for the refresh token.')
        netatmoLogger.error(' - save the %s file.', TOKEN_FILENAME)
        netatmoLogger.error('_______________________________________________________')
        sys.exit(1)

    def refresh_token(self):
        """NetAtmo API token refresh. Result: self.token and token.json file.

        Returns:
            bool: True if the token was refreshed
        """
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': self.token['refresh_token'],
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret'],
        }
        try:
            response = requests.post(
                "https://api.netatmo.com/oauth2/token",
                data=payload,
                timeout=30  # Add timeout
            )
            netatmoLogger.debug("%d %s", response.status_code, response.text)
            response.raise_for_status()
            self.token = response.json()
            utils.write_json(self.token, TOKEN_FILENAME)
            netatmoLogger.info("refresh_token() OK.")
            return True
        except requests.exceptions.HTTPError as e:
            netatmoLogger.warning("refresh_token() HTTPError")
            netatmoLogger.warning("%d %s", e.response.status_code, e.response.text)
            netatmoLogger.warning("refresh_token() failed. Need a new access token.")
            self.get_new_token_info()
        except requests.exceptions.RequestException:
            netatmoLogger.error("refresh_token() RequestException", exc_info=1)
        return False

    def get_station_data(self, allow_refresh=True):
        """Gets NetAtmo weather station data. Result: self.data and data.json file.

        On a 403 the token is refreshed and the request retried once.

        Returns:
            bool: True if fresh data was fetched
        """
        params = {
            'access_token': self.token['access_token'],
            'device_id': self.config['device_id']
        }
        try:
            response = requests.post(
                "https://api.netatmo.com/api/getstationsdata",
                params=params,
                timeout=30
            )
            netatmoLogger.debug("%d %s", response.status_code, response.text)
            response.raise_for_status()
            self.data = response.json()
            utils.write_json(self.data, DATA_FILENAME)

            self.check_location()
            return True

        except requests.exceptions.HTTPError as e:
            netatmoLogger.warning("get_station_data() HTTPError")
            netatmoLogger.warning("%d %s", e.response.status_code, e.response.text)
            if e.response.status_code == 403 and allow_refresh:
                netatmoLogger.info("get_station_data() calling refresh_token()")
                if self.refresh_token():
                    netatmoLogger.info("get_station_data() retrying")
                    return self.get_station_data(allow_refresh=False)
        except requests.exceptions.RequestException:
            netatmoLogger.error("get_station_data() RequestException:", exc_info=1)
        return False

    def check_config(self):
        """Check configuration validity"""
        # check directories
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.makedirs(DATA_DIR, exist_ok=True)

        # read config
        if os.path.isfile(CONFIG_FILENAME):
            self.config = utils.read_json(CONFIG_FILENAME)
            placeholders = [self.config.get(k, 'xxxx') == 'xxxx' for k in ('client_id', 'client_secret', 'device_id')]
            if any(placeholders):
                netatmoLogger.error("main() error:")
                netatmoLogger.error("Please edit %s and try again.", CONFIG_FILENAME)
                sys.exit(1)
            if self.config.get('refresh_time', 0) < 60:
                self.config['refresh_time'] = REFRESH_TIME_DEFAULT
        else:
            self.config = CONFIG_DEFAULT
            utils.write_json(self.config, CONFIG_FILENAME)
            netatmoLogger.error("main() error:")
            netatmoLogger.error("Please edit %s and try again.", CONFIG_FILENAME)
            sys.exit(1)

        # read last token    
        if os.path.isfile(TOKEN_FILENAME):
            self.token = utils.read_json(TOKEN_FILENAME)
        else:
            self.token = TOKEN_DEFAULT
            utils.write_json(self.token, TOKEN_FILENAME)
            self.get_new_token_info()

    def check_location(self):
        """Extracts the longitude, latitude and altitude from the station data"""
        if 'location' in self.data['body']['devices'][0]['place']:
            location = self.data['body']['devices'][0]['place']['location']
            location[0] = round(location[0], 4)  # Use 4 decimal places for lat/lon to avoid overly precise data
            location[1] = round(location[1], 4)
            altitude = self.data['body']['devices'][0]['place']['altitude']
            if 'location' not in self.config:
                self.config['location'] = {}
            
            location_changed = (
                'longitude' not in self.config['location']
                or self.config['location']['longitude'] != location[0]
                or self.config['location']['latitude'] != location[1]
                or self.config['location']['altitude'] != altitude
            )
            
            if location_changed:
                self.config['location']['longitude'] = location[0]
                self.config['location']['latitude'] = location[1]
                self.config['location']['altitude'] = altitude
                utils.write_json(self.config, CONFIG_FILENAME)
                netatmoLogger.warning(
                    "Station location updated in config.json: lon %f lat %f",
                    self.config['location']['longitude'],
                    self.config['location']['latitude']
                )

    def run(self):
        """Main loop - fetches data and updates display periodically"""
        self.check_config()

        netatmoLogger.info("Starting NetAtmo service with %d seconds refresh time.", self.config['refresh_time'])

        screen_type = self.config.get('screen_type', None)
        self.weather_display = display.WeatherDisplay(screen_type=screen_type)

        # Start from the last stored data so the display still works if the first fetch fails
        if os.path.isfile(DATA_FILENAME):
            self.data = utils.read_json(DATA_FILENAME)

        try:
            while True:
                try:
                    netatmoLogger.info("Fetching new station data.")
                    if not self.get_station_data():
                        netatmoLogger.warning("Station data fetch failed, using last known data.")

                    if self.data:
                        formatted = self.console_formatter.format(self.data)
                        if formatted:
                            netatmoLogger.info(formatted)

                    # Fetch weather data if needed (every 60 minutes)
                    current_time = time.time()
                    if current_time - self.last_weather_fetch >= self.weather_interval:
                        netatmoLogger.info("Fetching new weather and air quality data.")
                        self.weather_service.get_weather_data(self.config)
                        self.air_quality_service.get_aqi_data(self.config)
                        self.sunrise_service.get_sunrise_data(self.config)
                        self.last_weather_fetch = current_time

                    # Update display (station data passed directly, no re-read from disk)
                    self.weather_display.generate(station_data=self.data)

                except Exception as e:
                    netatmoLogger.error("Error in main loop: %s", e, exc_info=True)

                # During night hours sleep the display and wait longer between refreshes
                if _is_night():
                    self.weather_display.sleep_display()
                    sleep_time = max(self.config['refresh_time'], NIGHT_REFRESH_TIME)
                    netatmoLogger.info("Night mode: sleeping for %d seconds...", sleep_time)
                else:
                    sleep_time = self.config['refresh_time']
                    netatmoLogger.info("Sleeping for %d seconds...", sleep_time)

                time.sleep(sleep_time)

        except KeyboardInterrupt:
            netatmoLogger.info("Shutting down gracefully...")


def main():
    utils.setup_logging()
    NetatmoService().run()


if __name__ == '__main__':
    main()
