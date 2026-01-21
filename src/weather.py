# https://api.met.no/weatherapi/locationforecast/2.0/compact?altitude=353&lat=60.70833400000004&lon=10.611503000000067

import time
import os
import logging
import requests
import utils

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)  # Parent directory (project root)

CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")

weatherLogger = logging.getLogger(__name__)
weatherLogger.setLevel(logging.INFO)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')

weather_data_filename = os.path.join(DATA_DIR, "weather_data.json")
config_filename = os.path.join(CONFIG_DIR, "config.json")
g_config = dict()



def get_weather_data():
    """Gets weather data from met.no API. Result: weather_data.json file."""
    
    global weather_data_filename
    global config_filename

    g_config = utils.read_json(config_filename)

    params = {
        'altitude': g_config['location']['altitude'],
        'lat': g_config['location']['latitude'],
        'lon': g_config['location']['longitude']
    }

    try:
        response = requests.get("https://api.met.no/weatherapi/locationforecast/2.0/complete", params=params, headers={"User-Agent": "netatmo-weather-app/1.0"})
        weatherLogger.debug("%d %s", response.status_code, response.text)
        response.raise_for_status()
        weather_data = response.json()
        utils.write_json(weather_data, weather_data_filename)    
    except requests.exceptions.HTTPError as e:
        weatherLogger.warning("get_weather_data() HTTPError")
        weatherLogger.warning("%d %s", e.response.status_code, e.response.text)
    except requests.exceptions.RequestException:
        weatherLogger.error("get_weather_data() RequestException:", exc_info=1)

def startWeatherService():
    """Starts periodic weather data retrieval."""
    while True:
        weatherLogger.info("Fetching new weather data.")
        get_weather_data()
        time.sleep(60*60)  # Sleep for 60 min

if __name__ == '__main__':
    startWeatherService()