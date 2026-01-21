#!/usr/bin/env python3
"""display.py
Displays NetAtmo weather station data on a local screen
input: data.json file, result of NetAtmo getstationsdata API
screen: PaPiRus ePaper / eInk Screen HAT for Raspberry Pi - 2.7"
output: copy of the screen in file: image.bmp
"""

import os
import logging

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

import utils

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)  # Parent directory (project root)

# Constants
WHITE = 1
BLACK = 0
RED = 2

DEFAULT_FONT_FILE = os.path.join(BASE_DIR, 'assets', 'fonts', 'free-sans.ttf')

DEFAULT_DATA_FILENAME = os.path.join(BASE_DIR, 'data', 'data.json')
DEFAULT_WEATHER_DATA_FILENAME = os.path.join(BASE_DIR, 'data', 'weather_data.json')
DEFAULT_IMAGE_FILENAME = os.path.join(BASE_DIR, 'image.bmp')
DEFAULT_SYMBOLS_DIR = os.path.join(BASE_DIR, 'assets', 'symbols')

DEFAULT_IMAGE_WIDTH = 960
DEFAULT_IMAGE_HEIGHT = 540

FONT_SIZE_TEXT = 25
FONT_SIZE_TEMP = 50
FONT_SIZE_TIME = 15

WEATHER_SYMBOL_SIZE = (100, 100)

displayLogger = logging.getLogger(__name__)


class WeatherDisplay:
    """Class to handle weather display rendering"""
    
    def __init__(self, 
                 data_filename=DEFAULT_DATA_FILENAME,
                 weather_data_filename=DEFAULT_WEATHER_DATA_FILENAME,
                 image_filename=DEFAULT_IMAGE_FILENAME,
                 symbols_dir=DEFAULT_SYMBOLS_DIR,
                 image_width=DEFAULT_IMAGE_WIDTH,
                 image_height=DEFAULT_IMAGE_HEIGHT):
        """Initialize the WeatherDisplay
        
        Args:
            data_filename: Path to netatmo data JSON file
            weather_data_filename: Path to weather forecast JSON file
            image_filename: Output image filename
            symbols_dir: Directory containing weather symbol images
            image_width: Width of output image in pixels
            image_height: Height of output image in pixels
        """
        self.data_filename = data_filename
        self.weather_data_filename = weather_data_filename
        self.image_filename = image_filename
        self.symbols_dir = symbols_dir
        self.image_width = image_width
        self.image_height = image_height

        #Check/create symbols directory
        if not os.path.isfile(data_filename):
            displayLogger.error("No data file found: %s", data_filename)
            exit(1)

        if not os.path.isfile(weather_data_filename):
            displayLogger.error("No forecast data file found: %s", weather_data_filename)
            exit(1)

        if not os.path.isfile(image_filename):
            displayLogger.error("No image file found: %s", image_filename)
            exit(1)

        if not os.path.isfile(DEFAULT_FONT_FILE):
            displayLogger.error("No font file found: %s", DEFAULT_FONT_FILE)
            exit(1)
        
        # Data storage
        self.data = {}
        self.weather_data = {}
        self.image = None
    
    
    @staticmethod
    def trend_symbol(trend):
        """Unicode symbol for temperature trend
        
        Args:
            trend: Trend direction ('up', 'down', 'stable')
            
        Returns:
            Unicode arrow character
        """
        if trend == 'up':
            return '\u2197' # '↗' U+2197
        elif trend == 'down':
            return '\u2198' # '↘' U+2198
        elif trend == 'stable':
            return '\u2192' # '→' U+2192
        else:
            return ' '
    
    def _load_data(self):
        """Load data from JSON files
        
        Returns:
            bool: True if data loaded successfully
        """
        # Read netatmo data
        if os.path.isfile(self.data_filename):
            self.data = utils.read_json(self.data_filename)
        else:
            displayLogger.error("No data file")
            return False
        
        if "body" not in self.data:
            displayLogger.error("Bad data format")
            return False
        
        # Read weather data
        if os.path.isfile(self.weather_data_filename):
            self.weather_data = utils.read_json(self.weather_data_filename)
        else:
            displayLogger.error("No weather data file")
            return False
        
        if "properties" not in self.weather_data:
            displayLogger.error("Bad weather data format")
            return False
        
        return True
    
    def draw_image(self):
        """Draw the weather display image"""
        # Load data
        if not self._load_data():
            return
        
        # Prepare for drawing
        draw = ImageDraw.Draw(self.image)
        width, height = self.image.size

        # Load fonts
        font_text = ImageFont.truetype(DEFAULT_FONT_FILE, FONT_SIZE_TEXT)
        font_temp = ImageFont.truetype(DEFAULT_FONT_FILE, FONT_SIZE_TEMP)
        font_time = ImageFont.truetype(DEFAULT_FONT_FILE, FONT_SIZE_TIME)

        # Get units from user settings
        user_admin = self.data["body"]["user"]["administrative"]
        battery_percent = 'Bateria: ' + str(self.data['body']['devices'][0]['modules'][0]['battery_percent']) + ' |' 
        unit_temp = ['°C', '°F'][user_admin["unit"]]
        unit_rain = ['mm/h', 'in/h'][user_admin["unit"]]
        unit_wind = ['kph', 'mph', 'm/s', 'beaufort', 'knot'][user_admin["windunit"]]
        unit_humidity = '%'
        unit_co2 = 'ppm'

        # Extract and format sensor values
        indoor_temp_str, indoor_humidity_str, indoor_co2_str = self._get_indoor_data(unit_temp, unit_humidity, unit_co2)
        outdoor_temp_str, outdoor_humidity_str, rain_str, wind_str = self._get_outdoor_data(unit_temp, unit_humidity, unit_rain, unit_wind)
        
        data_time_str = "Aktualizowano  : " + utils.timestr(self.data["time_server"])
        
        # Get weather forecast data
        forecast_data = self._get_forecast_data()

        # Calculate text dimensions
        (width_indoor, height_indoor) = utils.textsize(indoor_temp_str, font=font_temp)
        (width_outdoor, height_outdoor) = utils.textsize(outdoor_temp_str, font=font_temp)
        (width_rain, height_rain) = utils.textsize(rain_str, font=font_temp)
        (width_time, height_time) = utils.textsize(data_time_str, font=font_time)
        (width_battery, height_battery) = utils.textsize(battery_percent, font=font_time)

        # Maximum text width
        txtwidth = max(width_indoor, width_outdoor, width_rain)
        txtheight = height_indoor

        # Calculate window positions
        first_window_x = int(width/8)
        first_window_y = int(height/8)
        second_window_x = int((width/2)+width/6)
        second_window_y = int(height/8)
        bottom_window_x = int(10)
        bottom_window_y = int(height/2+150)

        # Draw layout structure
        self._draw_layout(draw, width, height)

        # Draw temperatures
        draw.text((first_window_x, first_window_y), indoor_temp_str, fill=BLACK, font=font_temp)
        draw.text((second_window_x, second_window_y), outdoor_temp_str, fill=BLACK, font=font_temp)

        # Draw indoor humidity and CO2
        draw.text((second_window_x, second_window_y + (4*txtheight)), 
                  indoor_humidity_str + " / " + indoor_co2_str, fill=BLACK, font=font_text)

        # Draw time and battery
        draw.text((width - width_time - 5, 5), data_time_str, fill=BLACK, font=font_time)
        draw.text((width - width_time - width_battery - 10, 5), battery_percent, fill=BLACK, font=font_time)

        # Draw weather forecast
        if forecast_data:
            self._draw_forecast(forecast_data, bottom_window_x, bottom_window_y, width, unit_temp, font_text)
    
    def _get_indoor_data(self, unit_temp, unit_humidity, unit_co2):
        """Extract indoor sensor data
        
        Args:
            unit_temp: Temperature unit string
            unit_humidity: Humidity unit string
            unit_co2: CO2 unit string
            
        Returns:
            tuple: (temperature_str, humidity_str, co2_str)
        """
        indoor_temp_str = 'N/A'
        indoor_humidity_str = 'N/A'
        indoor_co2_str = 'N/A'
        
        device = self.data["body"]["devices"][0]
        if "dashboard_data" in device:
            indoor_data = device["dashboard_data"]
            indoor_temp_str = '{0:.1f}'.format(indoor_data["Temperature"]) + " " + unit_temp
            indoor_humidity_str = '{0:.1f}'.format(indoor_data["Humidity"]) + " " + unit_humidity
            if "temp_trend" in indoor_data:
                indoor_temp_str += self.trend_symbol(indoor_data["temp_trend"])
            indoor_co2_str = '{0:.1f}'.format(indoor_data["CO2"]) + " " + unit_co2
            if "pressure_trend" in indoor_data:
                indoor_co2_str += self.trend_symbol(indoor_data["pressure_trend"])
        
        return indoor_temp_str, indoor_humidity_str, indoor_co2_str
    
    def _get_outdoor_data(self, unit_temp, unit_humidity, unit_rain, unit_wind):
        """Extract outdoor sensor data
        
        Args:
            unit_temp: Temperature unit string
            unit_humidity: Humidity unit string
            unit_rain: Rain unit string
            unit_wind: Wind unit string
            
        Returns:
            tuple: (temperature_str, humidity_str, rain_str, wind_str)
        """
        outdoor_temp_str = 'N/A'
        outdoor_humidity_str = 'N/A'
        rain_str = 'N/A'
        wind_str = 'N/A'
        
        device = self.data["body"]["devices"][0]
        for module in device["modules"]:
            if "dashboard_data" in module:
                module_type = module["type"]
                module_data = module["dashboard_data"]
                if module_type == "NAModule1":
                    # Outdoor Module
                    outdoor_temp_str = '{0:.1f}'.format(module_data["Temperature"]) + " " + unit_temp
                    outdoor_humidity_str = '{0:.1f}'.format(module_data["Humidity"]) + " " + unit_humidity
                    if "temp_trend" in module_data:
                        outdoor_temp_str += self.trend_symbol(module_data["temp_trend"])
                elif module_type == "NAModule2":
                    # Wind Gauge
                    wind_str = '{0:.1f}'.format(module_data.get("WindStrength", 0)) + " " + unit_wind
                elif module_type == "NAModule3":
                    # Rain Gauge
                    rain_str = '{0:.1f}'.format(module_data.get("sum_rain_24", 0)) + " mm"
                elif module_type == "NAModule4":
                    # Optional indoor module
                    pass
        
        return outdoor_temp_str, outdoor_humidity_str, rain_str, wind_str
    
    def _get_forecast_data(self):
        """Extract weather forecast data
        
        Returns:
            list: List of forecast dictionaries or None
        """
        if "properties" not in self.weather_data:
            return None
        
        timeseries = self.weather_data["properties"]["timeseries"]
        if len(timeseries) <= 23:
            return None
        
        forecast_data = []
        for index in [0, 5, 11, 17, 23]:
            forecast = timeseries[index]
            forecast_details = forecast["data"]["next_6_hours"]["details"]
            forecast_data.append({
                'time': forecast["time"],
                'symbol_code': forecast["data"]["next_6_hours"]["summary"]["symbol_code"],
                'temp_min': forecast_details["air_temperature_min"],
                'temp_max': forecast_details["air_temperature_max"]
            })
        
        return forecast_data
    
    def _draw_layout(self, draw, width, height):
        """Draw the basic layout structure
        
        Args:
            draw: ImageDraw object
            width: Image width
            height: Image height
        """
        # Outer rectangle
        draw.rectangle((2, 2, width - 2, height - 2), fill=WHITE, outline=BLACK)
        
        # Main dividing lines
        draw.line((width/2, 2, width/2, height/2), fill=BLACK, width=2)
        draw.line((2, height/2, width-2, height/2), fill=BLACK, width=2)

        # Bottom window divisions
        for i in range(1, 5):
            x = i * width / 4
            draw.line((x, height/2, x, height-2), fill=BLACK, width=2)
    
    def _draw_forecast(self, forecast_data, bottom_window_x, bottom_window_y, width, unit_temp, font_text):
        """Draw weather forecast section
        
        Args:
            forecast_data: List of forecast dictionaries
            bottom_window_x: X position of bottom window
            bottom_window_y: Y position of bottom window
            width: Image width
            unit_temp: Temperature unit string
            font_text: Font for text
        """
        draw = ImageDraw.Draw(self.image)
        
        for i, forecast in enumerate(forecast_data):
            # Load and resize weather symbol
            symbol_path = os.path.join(self.symbols_dir, forecast['symbol_code'] + ".png")
            if os.path.isfile(symbol_path):
                weather_symbol = Image.open(symbol_path)
                weather_symbol = weather_symbol.resize(WEATHER_SYMBOL_SIZE)
                
                # Calculate position
                x_pos = 60 + i * 240
                self.image.paste(weather_symbol, (x_pos, 300), mask=weather_symbol)
            
            # Draw time and temperature
            x_text = bottom_window_x + i * (width / 4)
            draw.text((x_text, bottom_window_y), utils.format_time_str(forecast['time']), 
                     fill=BLACK, font=font_text)
            temp_str = '{0:.1f}'.format(forecast['temp_min']) + unit_temp + " / " + \
                      '{0:.1f}'.format(forecast['temp_max']) + unit_temp
            draw.text((x_text, bottom_window_y + 30), temp_str, fill=BLACK, font=font_text)
    
    def add_humidity_icon(self):
        """Add humidity icon to the display"""
        humidity_path = os.path.join(self.symbols_dir, "humidity.png")
        if os.path.isfile(humidity_path):
            humidity = Image.open(humidity_path)
            self.image.paste(humidity, (600, 225), mask=humidity)
    
    def save(self):
        """Save the image to file"""
        if self.image:
            self.image.save(self.image_filename)
            displayLogger.info("Image saved to %s", self.image_filename)
    
    def generate(self):
        """Generate the complete weather display image
        
        This is the main method to create and save the display
        """
        # Create blank image
        self.image = Image.new('1', (self.image_width, self.image_height), WHITE)
        
        # Draw the weather data
        self.draw_image()
        
        # Add additional icons
        # self.add_humidity_icon()
        
        # Save the result
        self.save()


def main():
    """Main function"""
    display = WeatherDisplay()
    display.generate()


# main
if __name__ == '__main__':
    main()

"""
Usage Examples:

# Basic usage with defaults:
display = WeatherDisplay()
display.generate()

# Custom configuration:
display = WeatherDisplay(
    data_filename='custom/data.json',
    weather_data_filename='custom/weather.json',
    image_filename='my_display.bmp',
    symbols_dir='custom_symbols',
    font_file='/path/to/custom_font.ttf',
    image_width=1200,
    image_height=600
)
display.generate()

# Step-by-step generation:
display = WeatherDisplay()
display.image = Image.new('1', (display.image_width, display.image_height), WHITE)
display.draw_image()
display.add_humidity_icon()
# Add custom elements here...
display.save()
"""
