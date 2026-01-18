#!/usr/bin/env python3
"""netatmo.py
NetAtmo weather station display
Every 10 minutes, gets the weather station data to a
local data.json file, and calls display.py.
"""

import logging
import os
import sys
import threading
import time

import requests

import display
import utils
import weather

netatmoLogger = logging.getLogger(__name__)
netatmoLogger.setLevel(logging.INFO)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')

stop_event = threading.Event()

# JSON file names
CONFIG_FILENAME = "config/config.json"
TOKEN_FILENAME = "config/token.json"
DATA_FILENAME = "data/data.json"

# Default values
CONFIG_DEFAULT = '{"client_id": "xxxx", "client_secret": "xxxx", "device_id": "xxxx", "refresh_time": 600}, "location": {"longitude": 0.0, "latitude": 0.0, "altitude": 0}}'
TOKEN_DEFAULT = '{"access_token": "xxxx", "refresh_token": "xxxx"}'
REFRESH_TIME_DEFAULT = 600   # default 10 minutes


class NetatmoService:
    """Service for managing Netatmo weather station data."""  # Add docstring
    
    def __init__(self):
        self.config = {}  # Instead of dict()
        self.token = {}   # Instead of dict()
        self.data = {}    # Instead of dict()

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

            if 'location' in self.data['body']['devices'][0]['place']:
                location = self.data['body']['devices'][0]['place']['location']
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

    def display_console(self):
        """Displays weather data on the console. Input: self.data"""
        if "body" not in self.data:
            netatmoLogger.info("No data")
            return
        
        parts = [f"Time {utils.timestr(self.data['time_server'])}"]
        device = self.data["body"]["devices"][0]
        
        # Add device data
        parts.extend(self._format_device_data(device))
        
        # Add module data
        for module in device.get("modules", []):
            parts.extend(self._format_module_data(module))
        
        netatmoLogger.info(" | ".join(parts))

    def _format_device_data(self, device):
        """Format main device sensor data."""
        parts = []
        dashboard = device.get("dashboard_data", {})
        
        if "Pressure" in dashboard:
            parts.append(f"Pressure {dashboard['Pressure']}")
        if "Temperature" in dashboard:
            parts.append(f"Indoor {dashboard['Temperature']}")
        
        return parts

    def _format_module_data(self, module):
        """Format module sensor data based on module type."""
        if "dashboard_data" not in module:
            return []
        
        module_type = module["type"]
        dashboard = module["dashboard_data"]
        
        formatters = {
            "NAModule1": self._format_outdoor,
            "NAModule2": self._format_wind,
            "NAModule3": self._format_rain,
            "NAModule4": self._format_optional_indoor,
        }
        
        formatter = formatters.get(module_type)
        return formatter(module, dashboard) if formatter else []

    def _format_outdoor(self, module, dashboard):
        """Format outdoor module data."""
        if "Temperature" in dashboard:
            return [f"Outdoor {dashboard['Temperature']}"]
        return []

    def _format_wind(self, module, dashboard):
        """Format wind gauge data."""
        parts = []
        if "WindStrength" in dashboard:
            wind_str = f"Wind {dashboard['WindStrength']}"
            if "WindAngle" in dashboard:
                wind_str += f" angle {dashboard['WindAngle']}"
            parts.append(wind_str)
        return parts

    def _format_rain(self, module, dashboard):
        """Format rain gauge data."""
        if "Rain" in dashboard:
            return [f"Rain {dashboard['Rain']}"]
        return []

    def _format_optional_indoor(self, module, dashboard):
        """Format optional indoor module data."""
        module_name = module.get("module_name", "Opt Indoor")
        if "Temperature" in dashboard:
            return [f"{module_name} {dashboard['Temperature']}"]
        return []

    def check_config(self):
        """Check configuration validity"""
        # check directories
        if not os.path.isdir("config"):
            os.mkdir("config")
        if not os.path.isdir("data"):
            os.mkdir("data")

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

    def start(self):
        """Main function"""
        self.check_config()

        print("Starting NetAtmo service...")
        print(self.config['refresh_time'], "seconds refresh time.")

        # read last data
        if os.path.isfile(DATA_FILENAME):
            self.data = utils.read_json(DATA_FILENAME)
        
        while not stop_event.is_set():
            self.get_station_data()
            weather.get_weather_data()
            self.display_console()
            display.main()

            # sleep in small chunks so shutdown is responsive
            for _ in range(self.config['refresh_time']):
                if stop_event.is_set():
                    break
                time.sleep(1)


if __name__ == '__main__':
    service = NetatmoService()
    service.start()
