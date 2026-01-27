#!/usr/bin/env python3
"""netatmo.py
NetAtmo weather station display
Periodically fetches weather station data and updates the display.
"""

import logging
import os
import sys
import time

import requests

import display
import formatters
import reader
import utils
import weather

netatmoLogger = logging.getLogger(__name__)
netatmoLogger.setLevel(logging.INFO)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)  # Parent directory (project root)

# JSON file names
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
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


class NetatmoService:
    """Service for managing Netatmo weather station data."""
    
    def __init__(self):
        self.config = {}
        self.token = {}
        self.data = {}
        self.reader = reader.DataReader(DATA_FILENAME)
        self.console_formatter = formatters.NetatmoConsoleFormatter()
        self.weather_service = weather.WeatherServiceMetNo()
        self.air_quality_service = weather.AirQualityServiceWAQI()
        self.last_weather_fetch = 0
        self.weather_interval = 3600  # Fetch weather every 60 minutes

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
        """NetAtmo API token refresh. Result: self.token and token.json file."""
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
        except requests.exceptions.HTTPError as e:
            netatmoLogger.warning("refresh_token() HTTPError")
            netatmoLogger.warning("%d %s", e.response.status_code, e.response.text)
            netatmoLogger.warning("refresh_token() failed. Need a new access token.")
            self.get_new_token_info()
            return
        except requests.exceptions.RequestException:
            netatmoLogger.error("refresh_token() RequestException", exc_info=1)

    def get_station_data(self):
        """Gets NetAtmo weather station data. Result: self.data and data.json file."""
        params = {
            'access_token': self.token['access_token'],
            'device_id': self.config['device_id']
        }
        try:
            response = requests.post(
                "https://api.netatmo.com/api/getstationsdata",
                params=params,
                timeout=30  # Add timeout
            )
            netatmoLogger.debug("%d %s", response.status_code, response.text)
            response.raise_for_status()
            self.data = response.json()
            utils.write_json(self.data, DATA_FILENAME)

            self.check_location()

        except requests.exceptions.HTTPError as e:
            netatmoLogger.warning("get_station_data() HTTPError")
            netatmoLogger.warning("%d %s", e.response.status_code, e.response.text)
            if e.response.status_code == 403:
                netatmoLogger.info("get_station_data() calling refresh_token()")
                self.refresh_token()
                # retry
                netatmoLogger.info("get_station_data() retrying")
                self.get_station_data()
        except requests.exceptions.RequestException:
            netatmoLogger.error("get_station_data() RequestException:", exc_info=1)

    def check_config(self):
        """Check configuration validity"""
        # check directories
        if not os.path.isdir(CONFIG_DIR):
            os.mkdir(CONFIG_DIR)
        if not os.path.isdir(DATA_DIR):
            os.mkdir(DATA_DIR)

        # read config
        if os.path.isfile(CONFIG_FILENAME):
            self.config = utils.read_json(CONFIG_FILENAME)
            if self.config['client_id'] == 'xxxx' or self.config['client_secret'] == 'xxxx' or self.config['device_id'] == 'xxxx':
                netatmoLogger.error("main() error:")
                netatmoLogger.error("Please edit %s and try again.", CONFIG_FILENAME)
                sys.exit(1)
            if 'refresh_time' not in self.config or self.config['refresh_time'] < 60:
                self.config['refresh_time'] = REFRESH_TIME_DEFAULT
        else:
            self.config = CONFIG_DEFAULT
            utils.write_json(self.config, CONFIG_FILENAME)
            netatmoLogger.error("main() error:")
            netatmoLogger.error("Please edit %s and try again.", CONFIG_FILENAME)

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
            if 'location' not in self.config:  # Fixed typo: was 'location '
                self.config['location'] = {}
            
            # Break up the long conditional
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
        
        try:
            while True:
                try:
                    # Fetch station data
                    netatmoLogger.info("Fetching new station data.")
                    self.get_station_data()

                    # Read and display station data
                    if self.reader.exists():
                        self.data = self.reader.read()
                        formatted = self.reader.display(self.console_formatter)
                        if formatted:
                            netatmoLogger.info(formatted)
                    
                    # Fetch weather data if needed (every 60 minutes)
                    current_time = time.time()
                    if current_time - self.last_weather_fetch >= self.weather_interval:
                        netatmoLogger.info("Fetching new weather and air quality data.")
                        self.weather_service.get_weather_data()
                        self.air_quality_service.get_aqi_data()
                        self.last_weather_fetch = current_time
                    
                    # Update display
                    display.main()
                    
                except Exception as e:
                    netatmoLogger.error("Error in main loop: %s", e, exc_info=True)
                
                # Sleep before next iteration
                netatmoLogger.info("Sleeping for %d seconds...", self.config['refresh_time'])
                time.sleep(self.config['refresh_time'])
                
        except KeyboardInterrupt:
            netatmoLogger.info("Shutting down gracefully...")

if __name__ == '__main__':
    service = NetatmoService()
    service.run()
