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

# Station data that is already in memory can be passed directly (skips reading data.json):
display.generate(station_data=data)

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

import hashlib
import importlib
import logging
import os
import sys
import time
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

import utils

BASE_DIR = utils.BASE_DIR

# Constants
WHITE = 1
BLACK = 0
RED = 2

DEFAULT_FONT_FILE = os.path.join(BASE_DIR, 'assets', 'fonts', 'free-sans.ttf')

DEFAULT_DATA_FILENAME = os.path.join(BASE_DIR, 'data', 'data.json')
DEFAULT_WEATHER_DATA_FILENAME = os.path.join(BASE_DIR, 'data', 'weather_data.json')
DEFAULT_AQI_DATA_FILENAME = os.path.join(BASE_DIR, 'data', 'aqi_data.json')
DEFAULT_SUNRISE_DATA_FILENAME = os.path.join(BASE_DIR, 'data', 'sunrise_data.json')
DEFAULT_IMAGE_FILENAME = os.path.join(BASE_DIR, 'image.bmp')
DEFAULT_SYMBOLS_DIR = os.path.join(BASE_DIR, 'assets', 'symbols')

DEFAULT_IMAGE_WIDTH = 648
DEFAULT_IMAGE_HEIGHT = 480

FONT_SIZE_TEXT = 28
FONT_SIZE_TEMP = 51
FONT_SIZE_TIME = 18
FONT_SIZE_SMALL = 20

BATTERY_LABEL = 'Bateria'
STALE_DATA_SECONDS = 30 * 60   # station data older than this is flagged on the display
FORECAST_HOURS = 24

# E-paper refresh policy: a refresh flashes the whole panel, so skip it when the picture is
# unchanged, but still redraw now and then to clear ghosting.
FORCE_REFRESH_SECONDS = 6 * 60 * 60

TREND_SYMBOLS = {
    'up': '↗',     # ↗
    'down': '↘',   # ↘
    'stable': '→'  # →
}

# Unit options based on Netatmo API settings
UNIT_OPTIONS = {
    'temperature': ['°C', '°F'],
    'rain': ['mm/h', 'in/h'],
    'wind': ['kph', 'mph', 'm/s', 'beaufort', 'knot'],
    'pressure': ['mbar', 'inHg', 'mmHg']
}

displayLogger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def get_font(size):
    """Return the default font at the given size (loaded once per size)."""
    return ImageFont.truetype(DEFAULT_FONT_FILE, size)


@lru_cache(maxsize=256)
def load_symbol(symbols_dir, symbol_code, size):
    """Load a weather symbol, resized and colour-inverted. Cached per (dir, code, size).

    Returns:
        The prepared PIL image, or None if the symbol file does not exist.
    """
    symbol_path = os.path.join(symbols_dir, f"{symbol_code}.png")
    if not os.path.isfile(symbol_path):
        return None

    symbol = Image.open(symbol_path).resize(size)

    # Invert the symbol colors (black background, white symbols), keeping alpha
    if symbol.mode == 'RGBA':
        r, g, b, a = symbol.split()
        r, g, b = ImageOps.invert(Image.merge('RGB', (r, g, b))).split()
        return Image.merge('RGBA', (r, g, b, a))
    if symbol.mode == 'RGB':
        return ImageOps.invert(symbol)
    # grayscale or binary images
    return ImageOps.invert(symbol.convert('L'))


def _unit(kind, index):
    """Look up a unit string; fall back to the default unit for unknown settings."""
    options = UNIT_OPTIONS[kind]
    return options[index] if 0 <= index < len(options) else options[0]


def _clock(date_str, hm, tzinfo):
    """Build a datetime from a 'YYYY-MM-DD' date and an 'HH:MM' string in the given timezone."""
    return datetime.strptime(f"{date_str} {hm}", '%Y-%m-%d %H:%M').replace(tzinfo=tzinfo)


class WeatherDisplay:
    """Class to handle weather display rendering"""

    def __init__(self,
                 data_filename=DEFAULT_DATA_FILENAME,
                 weather_data_filename=DEFAULT_WEATHER_DATA_FILENAME,
                 aqi_data_filename=DEFAULT_AQI_DATA_FILENAME,
                 sunrise_data_filename=DEFAULT_SUNRISE_DATA_FILENAME,
                 image_filename=DEFAULT_IMAGE_FILENAME,
                 symbols_dir=DEFAULT_SYMBOLS_DIR,
                 image_width=DEFAULT_IMAGE_WIDTH,
                 image_height=DEFAULT_IMAGE_HEIGHT,
                 screen_type=None):
        """Initialize the WeatherDisplay

        Args:
            data_filename: Path to netatmo data JSON file
            weather_data_filename: Path to weather forecast JSON file
            aqi_data_filename: Path to air quality data JSON file
            sunrise_data_filename: Path to sunrise/sunset JSON file
            image_filename: Output image filename
            symbols_dir: Directory containing weather symbol images
            image_width: Width of output image in pixels
            image_height: Height of output image in pixels
            screen_type: Screen type ('epd2in7', 'epd5in83', 'epd5in83_V2', 'epd5in83b_V2', None for file only)
        """
        self.data_filename = data_filename
        self.weather_data_filename = weather_data_filename
        self.aqi_data_filename = aqi_data_filename
        self.sunrise_data_filename = sunrise_data_filename
        self.image_filename = image_filename
        self.symbols_dir = symbols_dir
        self.image_width = image_width
        self.image_height = image_height
        self.screen_type = screen_type
        self.epd = None
        self.units = {}  # Will be populated when data is loaded

        # Data storage
        self.data = {}
        self.weather_data = {}
        self.aqi_data = {}
        self.sunrise_data = {}
        self.image = None
        self.draw = None

        # E-paper refresh state
        self._asleep = False
        self._last_image_hash = None
        self._last_refresh = 0.0

        if not os.path.isfile(DEFAULT_FONT_FILE):
            raise FileNotFoundError(f"No font file found: {DEFAULT_FONT_FILE}")

    # ------------------------------------------------------------------ data

    def _read_optional(self, filename, label):
        """Read an optional JSON file; returns {} if missing."""
        if os.path.isfile(filename):
            return utils.read_json(filename)
        displayLogger.info("No %s file (optional)", label)
        return {}

    def _load_data(self, station_data=None):
        """Load data from JSON files (or use the given station data)

        Args:
            station_data: Netatmo getstationsdata response already in memory

        Returns:
            bool: True if the required data is available
        """
        if station_data:
            self.data = station_data
        elif os.path.isfile(self.data_filename):
            self.data = utils.read_json(self.data_filename)
        else:
            displayLogger.error("No data file found: %s", self.data_filename)
            return False

        devices = self.data.get("body", {}).get("devices")
        if not devices:
            displayLogger.error("Bad data format")
            return False
        if "dashboard_data" not in devices[0]:
            displayLogger.error("dashboard_data missing in data")
            return False

        # Forecast is optional: it may not have been fetched yet
        self.weather_data = self._read_optional(self.weather_data_filename, "forecast data")
        if self.weather_data and "properties" not in self.weather_data:
            displayLogger.error("Bad weather data format")
            self.weather_data = {}

        self.aqi_data = self._read_optional(self.aqi_data_filename, "AQI data")
        if self.aqi_data and self.aqi_data.get('status') != 'ok':
            displayLogger.warning("AQI data status not ok")
            self.aqi_data = {}

        self.sunrise_data = self._read_optional(self.sunrise_data_filename, "sunrise data")
        return True

    def _get_units(self):
        """Extract units from user settings.

        Returns:
            dict: Dictionary with unit strings for different measurements
        """
        user_admin = self.data["body"]["user"]["administrative"]

        return {
            'temp': _unit('temperature', user_admin.get("unit", 0)),
            'rain': _unit('rain', user_admin.get("unit", 0)),
            'wind': _unit('wind', user_admin.get("windunit", 0)),
            'pressure': _unit('pressure', user_admin.get("pressureunit", 0)),
            'humidity': '%',
            'co2': 'ppm'
        }

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

        for module in self.data["body"]["devices"][0].get("modules", []):
            if "dashboard_data" not in module:
                continue

            module_type = module["type"]
            data = module["dashboard_data"]

            if module_type == "NAModule1":  # Outdoor Module
                outdoor_data['temperature'] = data.get("Temperature")
                outdoor_data['humidity'] = data.get("Humidity")
                outdoor_data['temp_trend'] = data.get("temp_trend")
                outdoor_data['name'] = module.get('module_name')

            elif module_type == "NAModule2":  # Wind Gauge
                outdoor_data['wind'] = data.get("WindStrength", 0)

            elif module_type == "NAModule3":  # Rain Gauge
                outdoor_data['rain'] = data.get("sum_rain_24", 0)

        return outdoor_data

    def _get_battery_percent(self):
        """Battery level of the outdoor module (falls back to the first module), or None."""
        modules = self.data["body"]["devices"][0].get("modules", [])
        outdoor = next((m for m in modules if m.get("type") == "NAModule1"), None)
        module = outdoor or (modules[0] if modules else None)
        return module.get("battery_percent") if module else None

    def _get_forecast_data(self, current_outdoor_temp=None):
        """Extract hourly forecast data (temperature and weather symbol).

        If the current outdoor temperature is known, the forecast is shifted by the difference
        between measurement and the first forecast value to correct for forecast bias.

        Args:
            current_outdoor_temp: Current measured outdoor temperature for normalization

        Returns:
            list: List of forecast dictionaries, or None if there is not enough data
        """
        timeseries = self.weather_data.get("properties", {}).get("timeseries", [])
        if len(timeseries) < 10:
            return None

        offset = 0
        if current_outdoor_temp is not None:
            first_temp = timeseries[0]["data"]["instant"]["details"].get("air_temperature", 0)
            offset = current_outdoor_temp - first_temp
            displayLogger.info("Normalizing forecast: current=%.1f, forecast=%.1f, offset=%+.1f",
                               current_outdoor_temp, first_temp, offset)

        forecast_data = []
        for forecast in timeseries[:FORECAST_HOURS]:
            data = forecast["data"]

            # Weather symbol from 3-hour forecast if available, fallback to 1-hour
            symbol_code = None
            for period in ("next_3_hours", "next_1_hours"):
                if period in data:
                    symbol_code = data[period]["summary"]["symbol_code"]
                    break
            if not symbol_code:
                continue

            temp = data["instant"]["details"].get("air_temperature", 0)
            # Convert UTC time to local timezone
            forecast_time = datetime.fromisoformat(forecast["time"].replace('Z', '+00:00'))

            forecast_data.append({
                'time': forecast_time.astimezone().isoformat(),
                'symbol_code': symbol_code,
                'temp': temp + offset
            })

        return forecast_data

    # --------------------------------------------------------------- drawing

    def draw_image(self, station_data=None):
        """Draw the weather display image onto self.image

        Returns:
            bool: False if the data needed for drawing is not available
        """
        if not self._load_data(station_data):
            return False

        self.draw = ImageDraw.Draw(self.image)
        width, height = self.image.size
        font_text = get_font(FONT_SIZE_TEXT)
        font_temp = get_font(FONT_SIZE_TEMP)

        self.units = self._get_units()

        indoor_data = self._get_indoor_data()
        outdoor_data = self._get_outdoor_data()

        # Forecast, normalized with current outdoor temperature
        forecast_data = self._get_forecast_data(outdoor_data.get('temperature'))

        # Calculate window positions
        left_x = width // 9
        right_x = width // 2 + width // 9
        top_y = height // 6

        self._draw_layout(width, height)
        self._draw_indoor_data(indoor_data, left_x, top_y, font_text, font_temp)
        self._draw_outdoor_data(outdoor_data, right_x, top_y, font_text, font_temp)
        self._draw_header(width)

        if forecast_data:
            self._draw_forecast(forecast_data, width)
        return True

    def _draw_header(self, width):
        """Draw battery level and the time of the station data (top right)."""
        font_time = get_font(FONT_SIZE_TIME)
        time_server = self.data['time_server']

        data_time_str = utils.timestr(time_server)
        if time.time() - time_server > STALE_DATA_SECONDS:
            data_time_str = f"! {data_time_str}"  # station data is outdated
        battery = self._get_battery_percent()
        battery_str = f'{BATTERY_LABEL}: {battery if battery is not None else "N/A"} |'

        width_time, _ = utils.textsize(data_time_str, font=font_time)
        width_battery, _ = utils.textsize(battery_str, font=font_time)
        self.draw.text((width - width_time - 25, 5), data_time_str, fill=BLACK, font=font_time, stroke_width=.35)
        self.draw.text((width - width_time - width_battery - 30, 5), battery_str, fill=BLACK, font=font_time, stroke_width=.35)

    @staticmethod
    def _format_reading(value, unit, fmt, trend=None):
        """Format a sensor value with unit and optional trend arrow; 'N/A' if missing."""
        if value is None:
            return 'N/A'
        text = f"{value:{fmt}} {unit}"
        if trend:
            text += TREND_SYMBOLS.get(trend, '')
        return text

    def _draw_indoor_data(self, indoor_data, left_x, top_y, font_text, font_temp):
        """Draw indoor sensor data on the display

        Args:
            indoor_data: Dictionary with indoor sensor values
            left_x: X position for text
            top_y: Y position for top text
            font_text: Font for regular text
            font_temp: Font for temperature text
        """
        if not indoor_data:
            return

        font_small = get_font(FONT_SIZE_SMALL)
        units = self.units

        temp_str = self._format_reading(indoor_data['temperature'], units['temp'], '.1f', indoor_data['temp_trend'])
        humidity_str = self._format_reading(indoor_data['humidity'], units['humidity'], '.0f')
        co2_str = self._format_reading(indoor_data['co2'], units['co2'], '.0f', indoor_data['pressure_trend'])

        _, height_temp = utils.textsize(temp_str, font=font_temp)

        if indoor_data['name']:
            self.draw.text((left_x, top_y - height_temp), indoor_data['name'], fill=BLACK, font=font_text)

        self.draw.text((left_x, top_y), temp_str, fill=BLACK, font=font_temp, stroke_width=.5)

        # Humidity and CO2
        self._paste_icon('humidity', left_x - 32, top_y + (3 * height_temp) - 5, (30, 30))
        self.draw.text((left_x - 20, top_y + (3 * height_temp)), f" {humidity_str}  CO₂: {co2_str}",
                       fill=BLACK, font=font_small, stroke_width=.6)

    def _draw_outdoor_data(self, outdoor_data, right_x, top_y, font_text, font_temp):
        """Draw outdoor sensor data on the display

        Args:
            outdoor_data: Dictionary with outdoor sensor values
            right_x: X position for text
            top_y: Y position for top text
            font_text: Font for regular text
            font_temp: Font for temperature text
        """
        if not outdoor_data:
            return

        font_small = get_font(FONT_SIZE_SMALL)
        units = self.units

        temp_str = self._format_reading(outdoor_data['temperature'], units['temp'], '.1f', outdoor_data['temp_trend'])
        humidity_str = self._format_reading(outdoor_data['humidity'], units['humidity'], '.0f')

        _, height_temp = utils.textsize(temp_str, font=font_temp)

        if outdoor_data['name']:
            self.draw.text((right_x, top_y - height_temp), outdoor_data['name'], fill=BLACK, font=font_text)

        self.draw.text((right_x, top_y), temp_str, fill=BLACK, font=font_temp, stroke_width=.5)

        # Humidity
        self._paste_icon('humidity', right_x + 50, top_y + (3 * height_temp) - 5, (30, 30))
        self.draw.text((right_x + 40, top_y + (3 * height_temp)), f" {humidity_str}",
                       fill=BLACK, font=font_small, stroke_width=.6)

        # AQI if available
        aqi_value = self.aqi_data.get('data', {}).get('aqi')
        if aqi_value is not None:
            self.draw.text((right_x + 140, top_y + (3 * height_temp)), f"AQI: {aqi_value}",
                           fill=BLACK, font=font_small, stroke_width=.6)

    def _draw_layout(self, width, height):
        """Draw the basic layout structure"""
        # Outer rectangle
        self.draw.rectangle((2, 2, width - 2, height - 2), fill=WHITE, outline=BLACK)

        # Main dividing lines
        mid_x = width // 2
        mid_y = height // 2
        self.draw.line((mid_x, 2, mid_x, mid_y), fill=BLACK, width=2)
        self.draw.line((2, mid_y, width - 2, mid_y), fill=BLACK, width=2)

    def _paste_icon(self, symbol_code, x_center, y_top, size):
        """Paste a weather symbol with its horizontal center at x_center and top edge at y_top."""
        symbol = load_symbol(self.symbols_dir, symbol_code, tuple(size))
        if symbol is not None:
            self.image.paste(symbol, (x_center - size[0] // 2, y_top), mask=symbol)

    def _draw_forecast_symbol(self, symbol_code, x, label_y, y, text_height, graph_top, graph_bottom, size):
        """Draw a forecast symbol next to its temperature label.

        The symbol goes above the label when the label sits above the curve point,
        otherwise below it, and is kept inside the graph area.
        """
        symbol_y = label_y - size[1] - 5 if label_y < y else label_y + text_height + 5
        symbol_y = max(graph_top - 50, min(symbol_y, graph_bottom - size[1]))
        self._paste_icon(symbol_code, x, symbol_y, size)

    def _draw_forecast(self, forecast_data, width):
        """Draw weather forecast section as a temperature curve graph

        Args:
            forecast_data: List of forecast dictionaries with hourly data
            width: Image width
        """
        draw = self.draw

        if not forecast_data or len(forecast_data) < 2:
            return

        # Graph dimensions and positioning
        graph_left = 50
        graph_right = width - 50
        graph_top = self.image_height // 2 + 20
        graph_bottom = self.image_height - 68  # leaves room for time labels, night bar and sun label
        graph_width = graph_right - graph_left
        graph_height = graph_bottom - graph_top

        # Temperature range with 10% padding on each side
        temps = [f['temp'] for f in forecast_data]
        min_temp = min(temps)
        max_temp = max(temps)
        temp_range = max_temp - min_temp if max_temp != min_temp else 10
        temp_padding = temp_range * 0.1
        min_temp -= temp_padding
        max_temp += temp_padding
        temp_range = max_temp - min_temp

        x_step = graph_width / (len(forecast_data) - 1)

        def temp_to_y(temp):
            # Invert y axis (higher temp = lower y)
            return int(graph_bottom - ((temp - min_temp) / temp_range * graph_height))

        def hour_to_x(hour_idx):
            return int(graph_left + (hour_idx * x_step))

        curve_points = [(hour_to_x(i), temp_to_y(f['temp'])) for i, f in enumerate(forecast_data)]
        draw.line(curve_points, fill=BLACK, width=5)

        font_small = get_font(22)
        font_tiny = get_font(16)

        for i, forecast in enumerate(forecast_data):
            x, y = curve_points[i]

            # Mark every 3 hours on x-axis
            if (i + 1) % 3 == 0:
                draw.line([(x, graph_bottom), (x, graph_bottom + 5)], fill=BLACK, width=3)

                hour_str = datetime.fromisoformat(forecast['time']).strftime('%H:%M')
                text_bbox = draw.textbbox((0, 0), hour_str, font=font_tiny)
                text_width = text_bbox[2] - text_bbox[0]
                draw.text((x - text_width // 2, graph_bottom + 8), hour_str, fill=BLACK, font=font_tiny, stroke_width=.3)

            # Label every 6 hours with temp and weather symbol
            if (i + 1) % 6 == 0:
                draw.ellipse([(x - 5, y - 5), (x + 5, y + 5)], fill=BLACK, outline=BLACK)

                temp_str = f"{forecast['temp']:.1f}{self.units['temp']}"
                text_bbox = draw.textbbox((0, 0), temp_str, font=font_small)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]

                # Position text above or below point depending on space
                label_y = y - text_height - 15 if y > graph_top + 60 else y + 15
                draw.text((x - text_width // 2, label_y), temp_str, fill=BLACK, font=font_small)

                self._draw_forecast_symbol(forecast['symbol_code'], x, label_y, y, text_height,
                                           graph_top, graph_bottom, (60, 60))

        self._draw_night_bar(forecast_data, graph_left, graph_bottom, hour_to_x)

    def _draw_night_bar(self, forecast_data, graph_left, graph_bottom, hour_to_x):
        """Draw a thin bar below the forecast x-axis showing nighttime (black) and daytime (white) periods.

        Also draws a small label with sunrise, sunset, and daylight duration for today.
        """
        if not forecast_data:
            return

        draw = self.draw
        bar_top = graph_bottom + 30
        bar_bottom = bar_top + 8
        font_tiny = get_font(14)

        times = [datetime.fromisoformat(f['time']) for f in forecast_data]
        tzinfo = times[0].tzinfo

        def sun_times(date_str):
            """(sunrise, sunset) datetimes for a date, or None if unknown."""
            day_data = self.sunrise_data.get(date_str)
            if not day_data or not day_data.get('sunrise') or not day_data.get('sunset'):
                return None
            return _clock(date_str, day_data['sunrise'], tzinfo), _clock(date_str, day_data['sunset'], tzinfo)

        def is_night(dt):
            sun = sun_times(dt.strftime('%Y-%m-%d'))
            if sun is None:
                return False  # No data — assume daytime
            return dt < sun[0] or dt >= sun[1]

        def time_to_x(target_dt):
            """Interpolate x coordinate for a datetime within the forecast range."""
            for i in range(len(times) - 1):
                if times[i] <= target_dt <= times[i + 1]:
                    frac = (target_dt - times[i]).total_seconds() / (times[i + 1] - times[i]).total_seconds()
                    return hour_to_x(i) + frac * (hour_to_x(i + 1) - hour_to_x(i))
            return None

        # Event times: forecast hours + exact sunrise/sunset moments
        event_times = list(times)
        for date_str in sorted({t.strftime('%Y-%m-%d') for t in times}):
            for evt in sun_times(date_str) or ():
                if times[0] <= evt <= times[-1]:
                    event_times.append(evt)
        event_times.sort()

        # One rectangle per event interval, coloured by the midpoint's night status
        for start, end in zip(event_times, event_times[1:]):
            if is_night(start + (end - start) / 2):
                x0, x1 = time_to_x(start), time_to_x(end)
                if x0 is not None and x1 is not None:
                    draw.rectangle([(int(x0), bar_top), (int(x1), bar_bottom)], fill=BLACK)

        draw.rectangle([(graph_left, bar_top), (hour_to_x(len(forecast_data) - 1), bar_bottom)], outline=BLACK, width=1)

        # Sunrise/sunset label for today
        sun = sun_times(times[0].strftime('%Y-%m-%d'))
        if sun:
            daylight_min = int((sun[1] - sun[0]).total_seconds() / 60)
            label = (f"↑{sun[0]:%H:%M}  ↓{sun[1]:%H:%M}  "
                     f"{daylight_min // 60}h {daylight_min % 60}m")
            draw.text((graph_left, bar_bottom + 2), label, fill=BLACK, font=font_tiny)

    # ---------------------------------------------------------------- screen

    def _init_screen(self):
        """Initialize the e-paper display based on screen_type.
        Only initializes once; subsequent calls return the cached dimensions.

        Returns:
            tuple: (width, height) for the screen, or None if file-only mode
        """
        if self.screen_type is None:
            return None

        if self.epd is not None:
            return (self.epd.width, self.epd.height)

        try:
            libdir = os.path.realpath(os.getenv('HOME', '.') + '/e-Paper/RaspberryPi_JetsonNano/python/lib')
            if libdir not in sys.path:
                sys.path.append(libdir)

            # Import the module dynamically based on screen_type
            module = importlib.import_module(f'waveshare_epd.{self.screen_type}')
            epd = module.EPD()
            epd.init()
            self.epd = epd
            self._asleep = False
            displayLogger.info("Initialized %s (%dx%d)", self.screen_type, epd.width, epd.height)
            return (epd.width, epd.height)

        except Exception as e:
            displayLogger.error("Failed to initialize %s: %s", self.screen_type, e, exc_info=True)
            return None

    def _needs_refresh(self, image_hash):
        """Decide whether the panel has to be redrawn.

        A refresh is skipped when the picture is identical to the one on screen, unless the
        last refresh is older than FORCE_REFRESH_SECONDS.
        """
        if image_hash != self._last_image_hash:
            return True
        return time.time() - self._last_refresh >= FORCE_REFRESH_SECONDS

    def _display_on_screen(self):
        """Display the image on the physical e-paper screen (full refresh, only when needed)."""
        if self.epd is None:
            return

        image_hash = hashlib.md5(self.image.tobytes()).hexdigest()
        if not self._needs_refresh(image_hash):
            displayLogger.info("Image unchanged, e-paper refresh skipped.")
            return

        try:
            # The panel only needs re-initialising after it was put to sleep
            if self._asleep:
                self.epd.init()
                self._asleep = False

            if 'b' in self.screen_type.lower() and hasattr(self.epd, 'display'):
                # 3-color displays need separate black and red images
                red_image = Image.new('1', (self.image_width, self.image_height), WHITE)
                self.epd.display(self.epd.getbuffer(self.image), self.epd.getbuffer(red_image))
            else:
                self.epd.display(self.epd.getbuffer(self.image))

            self._last_image_hash = image_hash
            self._last_refresh = time.time()
            displayLogger.info("Image displayed on %s (full refresh)", self.screen_type)

        except Exception as e:
            displayLogger.error("Failed to display on %s: %s", self.screen_type, e, exc_info=True)

    def sleep_display(self):
        """Put the e-paper display into deep sleep to save power.

        Call this when no update is expected for an extended period (e.g. night hours).
        The display is re-initialised automatically on the next refresh.
        """
        if self.epd is not None and not self._asleep and hasattr(self.epd, 'sleep'):
            self.epd.sleep()
            self._asleep = True
            displayLogger.info("Display sleeping.")

    def generate(self, station_data=None):
        """Generate the complete weather display image

        This is the main method to create and save the display

        Args:
            station_data: Netatmo getstationsdata response; read from data_filename if omitted
        """
        # Initialize screen if specified (no-op after first call)
        screen_size = self._init_screen()
        if screen_size:
            self.image_width, self.image_height = screen_size

        self.image = Image.new('1', (self.image_width, self.image_height), WHITE)

        if not self.draw_image(station_data):
            displayLogger.warning("Nothing to display, image not updated.")
            return

        self.image.save(self.image_filename)
        displayLogger.info("Image saved to %s", self.image_filename)

        if self.epd is not None:
            self._display_on_screen()


def main():
    """Main function"""
    utils.setup_logging()
    # Try to read screen_type from config
    config_file = os.path.join(utils.CONFIG_DIR, 'config.json')
    screen_type = None

    if os.path.isfile(config_file):
        try:
            screen_type = utils.read_json(config_file).get('screen_type', None)
        except Exception as e:
            displayLogger.warning("Could not read screen_type from config: %s", e)

    WeatherDisplay(screen_type=screen_type).generate()


if __name__ == '__main__':
    main()
