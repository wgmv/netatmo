#!/usr/bin/env python3
"""display.py
Displays NetAtmo weather station data on a local screen
input: data.json file, result of NetAtmo getstationsdata API
screen: Waveshare ePaper / eInk Screen HAT for Raspberry Pi
output: copy of the screen in file: image.bmp

Usage Examples:

# Basic usage with defaults (file-only mode):
display = WeatherDisplay()
display.generate()

# With Waveshare 2.7" e-paper display:
display = WeatherDisplay(screen_type='epd2in7')
display.generate()

# With Waveshare 5.83" e-paper display:
display = WeatherDisplay(screen_type='epd5in83b_V2')
display.generate()

# Custom configuration:
display = WeatherDisplay(
    data_filename='custom/data.json',
    weather_data_filename='custom/weather.json',
    image_filename='my_display.bmp',
    symbols_dir='custom_symbols',
    image_width=1200,
    image_height=600,
    screen_type='epd5in83b_V2'
)
display.generate()

# Configure via config.json by adding "screen_type" field:
# {
#   "client_id": "...",
#   "screen_type": "epd2in7"  // Options: "epd2in7", "epd5in83b_V2", or null
# }

# Supported screen_type values:
# - None or null: File-only mode (default)
# - 'epd2in7': Waveshare 2.7" e-paper HAT
# - 'epd5in83': Waveshare 5.83" e-paper HAT (B/W)
# - 'epd5in83_V2': Waveshare 5.83" e-paper HAT V2 (B/W)
# - 'epd5in83b_V2': Waveshare 5.83" e-paper HAT V2 (B/W/R)
"""

import os
import logging
import sys
import importlib
from datetime import datetime

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

CELSIUS_TO_KELVIN = 273.15

DEFAULT_FONT_FILE = os.path.join(BASE_DIR, 'assets', 'fonts', 'free-sans.ttf')

DEFAULT_DATA_FILENAME = os.path.join(BASE_DIR, 'data', 'data.json')
DEFAULT_WEATHER_DATA_FILENAME = os.path.join(BASE_DIR, 'data', 'weather_data.json')
DEFAULT_IMAGE_FILENAME = os.path.join(BASE_DIR, 'image.bmp')
DEFAULT_SYMBOLS_DIR = os.path.join(BASE_DIR, 'assets', 'symbols')

DEFAULT_IMAGE_WIDTH = 648
DEFAULT_IMAGE_HEIGHT = 480

FONT_SIZE_TEXT = 28
FONT_SIZE_TEMP = 55
FONT_SIZE_TIME = 18

TREND_SYMBOLS = {
    'up': '\u2197',     # ↗
    'down': '\u2198',   # ↘
    'stable': '\u2192'  # →
}

WEATHER_SYMBOL_SIZE = (100, 100)

# Unit options based on Netatmo API settings
UNIT_OPTIONS = {
    'temperature': ['°C', '°F'],
    'rain': ['mm/h', 'in/h'],
    'wind': ['kph', 'mph', 'm/s', 'beaufort', 'knot'],
    'pressure': ['mbar', 'inHg', 'mmHg']
}

displayLogger = logging.getLogger(__name__)


class WeatherDisplay:
    """Class to handle weather display rendering"""
    
    def __init__(self, 
                 data_filename=DEFAULT_DATA_FILENAME,
                 weather_data_filename=DEFAULT_WEATHER_DATA_FILENAME,
                 image_filename=DEFAULT_IMAGE_FILENAME,
                 symbols_dir=DEFAULT_SYMBOLS_DIR,
                 image_width=DEFAULT_IMAGE_WIDTH,
                 image_height=DEFAULT_IMAGE_HEIGHT,
                 screen_type=None):
        """Initialize the WeatherDisplay
        
        Args:
            data_filename: Path to netatmo data JSON file
            weather_data_filename: Path to weather forecast JSON file
            image_filename: Output image filename
            symbols_dir: Directory containing weather symbol images
            image_width: Width of output image in pixels
            image_height: Height of output image in pixels
            screen_type: Screen type ('epd2in7', 'epd5in83', 'epd5in83_V2', 'epd5in83b_V2', None for file only)
        """
        self.data_filename = data_filename
        self.weather_data_filename = weather_data_filename
        self.image_filename = image_filename
        self.symbols_dir = symbols_dir
        self.image_width = image_width
        self.image_height = image_height
        self.screen_type = screen_type
        self.epd = None
        self.units = {}  # Will be populated when data is loaded

        #Check/create symbols directory
        if not os.path.isfile(data_filename):
            displayLogger.error("No data file found: %s", data_filename)
            exit(1)

        if not os.path.isfile(weather_data_filename):
            displayLogger.error("No forecast data file found: %s", weather_data_filename)
            exit(1)

        if not os.path.isfile(DEFAULT_FONT_FILE):
            displayLogger.error("No font file found: %s", DEFAULT_FONT_FILE)
            exit(1)
        
        # Data storage
        self.data = {}
        self.weather_data = {}
        self.image = None

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
        if "dashboard_data" not in self.data["body"]["devices"][0]:
            displayLogger.error("dashboard_data missing in data")
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
    
    def _get_units(self):
        """Extract units from user settings.
        
        Returns:
            dict: Dictionary with unit strings for different measurements
        """
        user_admin = self.data["body"]["user"]["administrative"]
        
        return {
            'temp': UNIT_OPTIONS['temperature'][user_admin["unit"]],
            'rain': UNIT_OPTIONS['rain'][user_admin["unit"]],
            'wind': UNIT_OPTIONS['wind'][user_admin["windunit"]],
            'pressure': UNIT_OPTIONS['pressure'][user_admin.get("pressureunit", 0)],
            'humidity': '%',
            'co2': 'ppm'
        }
    
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
        self.units = self._get_units()

        # Extract sensor data
        indoor_data = self._get_indoor_data()
        outdoor_data = self._get_outdoor_data()
        
        # Get weather forecast data (normalized with current outdoor temperature)
        current_temp = outdoor_data.get('temperature') if outdoor_data else None
        forecast_data = self._get_forecast_data(current_temp)

        # Calculate window positions
        left_x = width // 8
        right_x = width // 2 + width // 6
        top_y = height // 6

        # Draw layout structure
        self._draw_layout(draw, width, height)

        # Draw indoor data
        self._draw_indoor_data(indoor_data, left_x, top_y, font_text, font_temp)
        
        # Draw outdoor data
        self._draw_outdoor_data(outdoor_data, right_x, top_y, font_text, font_temp)
        
        # Draw time and battery
        battery = self.data['body']['devices'][0]['modules'][0]['battery_percent']
        data_time_str = f"Aktualizowano  : {utils.timestr(self.data['time_server'])}"
        battery_percent = f'Bateria: {battery} |'
        (width_time, height_time) = utils.textsize(data_time_str, font=font_time)
        (width_battery, height_battery) = utils.textsize(battery_percent, font=font_time)
        draw.text((width - width_time - 5, 5), data_time_str, fill=BLACK, font=font_time)
        draw.text((width - width_time - width_battery - 10, 5), battery_percent, fill=BLACK, font=font_time)

        # Draw weather forecast
        if forecast_data:
            self._draw_forecast(forecast_data, width)
    
    def _get_indoor_data(self):
        """Extract indoor sensor data
        
        Returns:
            dict: Indoor sensor data with temperature, humidity, CO2, and trends
        """
        device = self.data["body"]["devices"][0]
        if "dashboard_data" not in device:
            return None
            
        data = device["dashboard_data"]
        
        return {
            'temperature': data.get("Temperature"),
            'humidity': data.get("Humidity"),
            'co2': data.get("CO2"),
            'temp_trend': data.get("temp_trend"),
            'pressure_trend': data.get("pressure_trend"),
            'name': device.get("module_name", "Indoor")
        }
    
    def _draw_indoor_data(self, indoor_data, left_x, top_y, font_text, font_temp):
        """Draw indoor sensor data on the display
        
        Args:
            indoor_data: Dictionary with indoor sensor values
            left_x: X position for left text
            right_x: X position for right text
            top_y: Y position for top text
            font_text: Font for regular text
            font_temp: Font for temperature text
        """
        if not indoor_data:
            return
            
        draw = ImageDraw.Draw(self.image)
        
        # Format temperature
        if indoor_data['temperature'] is not None:
            indoor_temp_str = f"{indoor_data['temperature']:.1f} {self.units['temp']}"
            if indoor_data['temp_trend']:
                indoor_temp_str += TREND_SYMBOLS.get(indoor_data['temp_trend'], '')
        else:
            indoor_temp_str = 'N/A'
        
        # Format humidity
        if indoor_data['humidity'] is not None:
            indoor_humidity_str = f"{indoor_data['humidity']:.1f} {self.units['humidity']}"
        else:
            indoor_humidity_str = 'N/A'
        
        # Format CO2
        if indoor_data['co2'] is not None:
            indoor_co2_str = f"{indoor_data['co2']:.1f} {self.units['co2']}"
            if indoor_data['pressure_trend']:
                indoor_co2_str += TREND_SYMBOLS.get(indoor_data['pressure_trend'], '')
        else:
            indoor_co2_str = 'N/A'
                    
        # Calculate text height for positioning
        (width_temp, height_temp) = utils.textsize(indoor_temp_str, font=font_temp)

        #Draw module name
        if indoor_data['name']:
            draw.text((left_x, top_y - height_temp), indoor_data['name'], fill=BLACK, font=font_text)
        
        # Draw temperature
        draw.text((left_x, top_y), indoor_temp_str, fill=BLACK, font=font_temp)

        
        # Draw humidity and CO2
        self._draw_weather_symbol('humidity', left_x - 42, top_y + (3 * height_temp) + 30, top_y + (4 * height_temp), height_temp, top_y, top_y + (3 * height_temp) + 30, symbol_size=(30, 30))
        draw.text((left_x - 30, top_y + (3 * height_temp)),  f" {indoor_humidity_str} / CO₂: {indoor_co2_str}", fill=BLACK, font=font_text)
        
    
    def _get_outdoor_data(self):
        """Extract outdoor sensor data
        
        Returns:
            dict: Outdoor sensor data including temperature, humidity, rain, wind, and trends
        """
        outdoor_data = {
            'temperature': None,
            'humidity': None,
            'temp_trend': None,
            'rain': None,
            'wind': None,
            'name': None
        }
        
        device = self.data["body"]["devices"][0]
        for module in device["modules"]:
            if "dashboard_data" not in module:
                continue
                
            module_type = module["type"]
            data = module["dashboard_data"]
            
            if module_type == "NAModule1":  # Outdoor Module
                outdoor_data['temperature'] = data.get("Temperature")
                outdoor_data['humidity'] = data.get("Humidity")
                outdoor_data['temp_trend'] = data.get("temp_trend")
                outdoor_data['name'] = module['module_name']
                
            elif module_type == "NAModule2":  # Wind Gauge
                outdoor_data['wind'] = data.get("WindStrength", 0)
                
            elif module_type == "NAModule3":  # Rain Gauge
                outdoor_data['rain'] = data.get("sum_rain_24", 0)
        
        return outdoor_data
    
    def _draw_outdoor_data(self, outdoor_data, right_x, top_y, font_text, font_temp):
        """Draw outdoor sensor data on the display
        
        Args:
            outdoor_data: Dictionary with outdoor sensor values
            right_x: X position for text
            top_y: Y position for top text
            font_temp: Font for temperature text
        """
        if not outdoor_data:
            return
            
        draw = ImageDraw.Draw(self.image)
        
        # Format temperature
        if outdoor_data['temperature'] is not None:
            outdoor_temp_str = f"{outdoor_data['temperature']:.1f} {self.units['temp']}"
            if outdoor_data['temp_trend']:
                outdoor_temp_str += TREND_SYMBOLS.get(outdoor_data['temp_trend'], '')
        else:
            outdoor_temp_str = 'N/A'

        # Format humidity
        if outdoor_data['humidity'] is not None:
            outdoor_humidity_str = f"{outdoor_data['humidity']:.1f} {self.units['humidity']}"
        else:
            outdoor_humidity_str = 'N/A'

        # Calculate text height for positioning
        (width_temp, height_temp) = utils.textsize(outdoor_temp_str, font=font_temp)

        #Draw module name
        if outdoor_data['name']:
            draw.text((right_x, top_y - height_temp), outdoor_data['name'], fill=BLACK, font=font_text)
        
        # Draw temperature
        draw.text((right_x, top_y), outdoor_temp_str, fill=BLACK, font=font_temp)

        # Draw humidity
        self._draw_weather_symbol('humidity', right_x + 25, top_y + (3 * height_temp) + 30, top_y + (4 * height_temp), height_temp, top_y, top_y + (3 * height_temp) + 30, symbol_size=(30, 30))

        draw.text((right_x + 35, top_y + (3 * height_temp)), f" {outdoor_humidity_str}", fill=BLACK, font=font_text)
        
    def _get_forecast_data(self, current_outdoor_temp=None):
        """Extract weather forecast data from instant section for each hour.
        
        Normalizes forecast temperatures based on current outdoor measurement to correct
        for forecast bias.
        
        Args:
            current_outdoor_temp: Current measured outdoor temperature for normalization
        
        Returns:
            list: List of forecast dictionaries with hourly temperature and 6-hour symbols
        """
        if "properties" not in self.weather_data:
            return None
        
        timeseries = self.weather_data["properties"]["timeseries"]
        if len(timeseries) < 10:
            return None
        
        forecast_data = []
        
        # Calculate temperature offset for normalization (as percentage)
        # Use Kelvin scale to avoid zero-crossing issues
        
        percent_offset = 0
        forecast_error = 0
        
        if current_outdoor_temp is not None and len(timeseries) > 0:
            # Get the first forecast temperature (current hour)
            first_forecast_temp = timeseries[0]["data"]["instant"]["details"].get("air_temperature", 0)
            forecast_error = current_outdoor_temp - first_forecast_temp
            
            # Convert to Kelvin for percentage calculation
            current_kelvin = current_outdoor_temp + CELSIUS_TO_KELVIN
            forecast_kelvin = first_forecast_temp + CELSIUS_TO_KELVIN
            
            # Calculate percentage offset on absolute scale
            percent_offset = (current_kelvin - forecast_kelvin) / forecast_kelvin
            
            displayLogger.info("Normalizing forecast: current=%.1f°C, forecast=%.1f°C, "
                             "error=%+.1f°C, offset=%+.2f%%",
                             current_outdoor_temp, first_forecast_temp, 
                             forecast_error, percent_offset * 100)
        
       
        for index in range(0,24):
            if index >= len(timeseries):
                continue
                
            forecast = timeseries[index]
            
            # Get temperature from instant section (current hour)
            instant_details = forecast["data"]["instant"]["details"]
            temp = instant_details.get("air_temperature", 0)
            
            # Apply normalization offset (percentage-based using Kelvin scale)
            if percent_offset != 0:
                temp_kelvin = temp + CELSIUS_TO_KELVIN
                normalized_kelvin = temp_kelvin * (1 + percent_offset)
                normalized_temp = normalized_kelvin - CELSIUS_TO_KELVIN
            else:
                normalized_temp = temp

            
            # Get weather symbol from 3-hour forecast if available, fallback to 1-hour
            symbol_code = None
            if "next_3_hours" in forecast["data"]:
                symbol_code = forecast["data"]["next_3_hours"]["summary"]["symbol_code"]
            elif "next_1_hours" in forecast["data"]:
                symbol_code = forecast["data"]["next_1_hours"]["summary"]["symbol_code"]
            
            if symbol_code:
                # Convert UTC time to local timezone
                forecast_time = datetime.fromisoformat(forecast["time"].replace('Z', '+00:00'))
                local_time = forecast_time.astimezone()
                
                forecast_data.append({
                    'time': local_time.isoformat(),
                    'symbol_code': symbol_code,
                    'temp': normalized_temp,
                    'original_temp': temp,
                    'error': forecast_error if index == 0 else None
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
        mid_x = width // 2
        mid_y = height // 2
        draw.line((mid_x, 2, mid_x, mid_y), fill=BLACK, width=2)
        draw.line((2, mid_y, width - 2, mid_y), fill=BLACK, width=2)

        # # Bottom window divisions (5 equal sections)
        # for i in range(1, 5):
        #     x = i * width // 4
        #     draw.line((x, mid_y, x, height - 2), fill=BLACK, width=2)
    
    def _draw_weather_symbol(self, symbol_code, x, label_y, y, text_height, graph_top, graph_bottom, symbol_size=(50, 50)):
        """Draw a weather symbol at the specified position
        
        Args:
            symbol_code: Weather symbol code (filename without .png)
            x: X position for center of symbol
            label_y: Y position of temperature label
            y: Y position of curve point
            text_height: Height of temperature text
            graph_top: Top boundary of graph
            graph_bottom: Bottom boundary of graph
            symbol_size: Tuple of (width, height) for symbol size
        """
        symbol_file = f"{symbol_code}.png"
        symbol_path = os.path.join(self.symbols_dir, symbol_file)
        
        if os.path.isfile(symbol_path):
            symbol = Image.open(symbol_path).resize(symbol_size)
            
            # Position symbol above the temperature label
            symbol_x = x - symbol_size[0] // 2
            symbol_y = label_y - symbol_size[1] - 5 if label_y < y else label_y + text_height + 5
            
            # Ensure symbol stays within bounds
            symbol_y = max(graph_top - 50, min(symbol_y, graph_bottom - symbol_size[1]))
            
            self.image.paste(symbol, (symbol_x, symbol_y), mask=symbol)
    
    def _draw_forecast(self, forecast_data, width):
        """Draw weather forecast section as a temperature curve graph
        
        Args:
            forecast_data: List of forecast dictionaries with hourly data
            bottom_window_x: X position of bottom window
            bottom_window_y: Y position of bottom window (not used, kept for compatibility)
            width: Image width
            font_text: Font for text
        """
        draw = ImageDraw.Draw(self.image)
        
        if not forecast_data or len(forecast_data) < 2:
            return
        
        # Graph dimensions and positioning
        graph_left = 50
        graph_right = width - 50
        graph_top = self.image_height // 2 + 20
        graph_bottom = self.image_height - 50
        graph_width = graph_right - graph_left
        graph_height = graph_bottom - graph_top
        
        # Extract temperatures for scaling
        temps = [f['temp'] for f in forecast_data]
        min_temp = min(temps)
        max_temp = max(temps)
        temp_range = max_temp - min_temp if max_temp != min_temp else 10
        
        # Add padding to temperature range (10% on each side)
        temp_padding = temp_range * 0.1
        min_temp -= temp_padding
        max_temp += temp_padding
        temp_range = max_temp - min_temp
        
        # Calculate x position for each hour
        hours_shown = len(forecast_data)
        x_step = graph_width / (hours_shown - 1) if hours_shown > 1 else graph_width
        
        # Helper function to convert temp to y coordinate
        def temp_to_y(temp):
            # Invert y axis (higher temp = lower y)
            normalized = (temp - min_temp) / temp_range
            return int(graph_bottom - (normalized * graph_height))
        
        # Helper function to convert hour index to x coordinate
        def hour_to_x(hour_idx):
            return int(graph_left + (hour_idx * x_step))
        
        # Draw temperature curve
        curve_points = []
        for i, forecast in enumerate(forecast_data):
            x = hour_to_x(i)
            y = temp_to_y(forecast['temp'])
            curve_points.append((x, y))
        
        # Draw the curve line
        if len(curve_points) > 1:
            draw.line(curve_points, fill=BLACK, width=5)
        
        # Draw markers and labels
        font_small = ImageFont.truetype(DEFAULT_FONT_FILE, 22)
        font_tiny = ImageFont.truetype(DEFAULT_FONT_FILE, 16)
        
        for i, forecast in enumerate(forecast_data):
            x = hour_to_x(i)
            y = temp_to_y(forecast['temp'])
            
            # Mark every 3 hours on x-axis
            if i % 3 == 0:
                # Draw tick mark
                draw.line([(x, graph_bottom), (x, graph_bottom + 5)], fill=BLACK, width=3)
                
                # Draw hour label
                time_obj = datetime.fromisoformat(forecast['time'])
                hour_str = time_obj.strftime('%H:%M')
                text_bbox = draw.textbbox((0, 0), hour_str, font=font_tiny)
                text_width = text_bbox[2] - text_bbox[0]
                draw.text((x - text_width // 2, graph_bottom + 8), hour_str, fill=BLACK, font=font_tiny)
            
            # Label every 6 hours with temp and weather symbol
            if i % 6 == 0:
                # Draw point on curve
                draw.ellipse([(x - 5, y - 5), (x + 5, y + 5)], fill=BLACK, outline=BLACK)
                
                # Draw temperature label
                temp_str = f"{forecast['temp']:.1f}{self.units['temp']}"
                text_bbox = draw.textbbox((0, 0), temp_str, font=font_small)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                # Position text above or below point depending on space
                label_y = y - text_height - 15 if y > graph_top + 60 else y + 15
                draw.text((x - text_width // 2, label_y), temp_str, fill=BLACK, font=font_small)
                
                # Draw weather symbol
                self._draw_weather_symbol(forecast['symbol_code'], x, label_y, y, text_height, 
                                         graph_top, graph_bottom, symbol_size=(60, 60))
        
        # Draw graph border
        # draw.rectangle([(graph_left, graph_top), (graph_right, graph_bottom)], outline=BLACK, width=2)
    
    
    def _init_screen(self):
        """Initialize the e-paper display based on screen_type
        
        Returns:
            tuple: (width, height) for the screen, or None if file-only mode
        """
        if self.screen_type is None:
            return None
        
        try:
            libdir = os.path.realpath(os.getenv('HOME', '.') + '/e-Paper/RaspberryPi_JetsonNano/python/lib')
            if libdir not in sys.path:
                sys.path.append(libdir)
            
            # Import the module dynamically based on screen_type
            module = importlib.import_module(f'waveshare_epd.{self.screen_type}')
            epd = module.EPD()
            epd.init()
            self.epd = epd
            return (epd.width, epd.height)
        
        except Exception as e:
            displayLogger.error("Failed to initialize %s: %s", self.screen_type, e, exc_info=True)
            return None
    
    def _display_on_screen(self):
        """Display the image on the physical e-paper screen"""
        if self.epd is None:
            return
        
        try:
            # Check if this is a 3-color display (with red)
            if 'b' in self.screen_type.lower() and hasattr(self.epd, 'display'):
                # 3-color displays need separate black and red images
                # For simplicity, use the same image for black and a blank image for red
                black_image = self.image
                red_image = Image.new('1', (self.image_width, self.image_height), WHITE)
                self.epd.display(self.epd.getbuffer(black_image), self.epd.getbuffer(red_image))
            else:
                # 2-color displays (black and white only)
                self.epd.display(self.epd.getbuffer(self.image))
            
            self.epd.sleep()
            displayLogger.info("Image displayed on %s", self.screen_type)
        
        except Exception as e:
            displayLogger.error("Failed to display on %s: %s", self.screen_type, e, exc_info=True)
    
    def generate(self):
        """Generate the complete weather display image
        
        This is the main method to create and save the display
        """
        # Initialize screen if specified
        screen_size = self._init_screen()
        if screen_size:
            self.image_width, self.image_height = screen_size
            displayLogger.info("Using screen %s with size %s", self.screen_type, screen_size)
        
        # Create blank image
        self.image = Image.new('1', (self.image_width, self.image_height), WHITE)
        
        # Draw the weather data
        self.draw_image()
        
        # Save the result
        self.image.save(self.image_filename)
        displayLogger.info("Image saved to %s", self.image_filename)
        
        # Display on physical screen if available
        if self.epd is not None:
            self._display_on_screen()


def main():
    """Main function"""
    # Try to read screen_type from config
    config_file = os.path.join(BASE_DIR, 'config', 'config.json')
    screen_type = None
    
    if os.path.isfile(config_file):
        try:
            config = utils.read_json(config_file)
            screen_type = config.get('screen_type', None)
        except Exception as e:
            displayLogger.warning("Could not read screen_type from config: %s", e)
    
    display = WeatherDisplay(screen_type=screen_type)
    display.generate()


# main
if __name__ == '__main__':
    main()
