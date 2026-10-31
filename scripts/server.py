"""server.py
Runs the Netatmo display service in a background thread and serves the rendered
image over HTTP (http://<host>:8000/image.bmp) plus a condensed /weather.json.
"""

import http.server
import json
import logging
import os
import socketserver
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import display  # noqa: E402
import netatmo  # noqa: E402
import utils  # noqa: E402

serverLogger = logging.getLogger("server")

PORT = 8000
WEATHER_DATA_FILENAME = os.path.join(utils.DATA_DIR, "weather_data.json")
FORECAST_STEPS = (0, 6, 12, 18)  # hours from now that are included in /weather.json


def build_forecast():
    """Condensed met.no forecast: one 6-hour summary every 6 hours."""
    if not os.path.isfile(WEATHER_DATA_FILENAME):
        serverLogger.error("No weather data file")
        return []
    timeseries = utils.read_json(WEATHER_DATA_FILENAME).get("properties", {}).get("timeseries", [])
    if len(timeseries) < 18:
        return []

    forecast = []
    for index in FORECAST_STEPS:
        entry = timeseries[index]
        item = {"time": entry["time"]}
        period = entry["data"].get("next_6_hours")
        if period:
            details = period["details"]
            item.update({
                "summary": period["summary"]["symbol_code"],
                "min_temp": details["air_temperature_min"],
                "max_temp": details["air_temperature_max"],
                "precipitation_amount": details["precipitation_amount"],
                "precipitation_amount_max": details.get("precipitation_amount_max"),
                "precipitation_amount_min": details.get("precipitation_amount_min"),
            })
        forecast.append(item)
    return forecast


def build_netatmo_summary():
    """Condensed current readings from the stored Netatmo data."""
    if not os.path.isfile(netatmo.DATA_FILENAME):
        return {}
    device = utils.read_json(netatmo.DATA_FILENAME)["body"]["devices"][0]
    main = device["dashboard_data"]
    summary = {
        "indoor_temperature": main["Temperature"],
        "indoor_humidity": main["Humidity"],
    }
    for module in device.get("modules", []):
        data = module.get("dashboard_data")
        if not data:
            continue
        if module["type"] == "NAModule1":
            summary["outdoor_temperature"] = data["Temperature"]
            summary["outdoor_humidity"] = data["Humidity"]
        elif module["type"] == "NAModule3":
            summary["rain"] = data["sum_rain_24"]
        elif module["type"] == "NAModule2":
            summary["wind_strength"] = data["WindStrength"]
            summary["wind_angle"] = data["WindAngle"]
    return summary


class WeatherHandler(http.server.BaseHTTPRequestHandler):
    def _send(self, status, content_type=None, body=b""):
        self.send_response(status)
        if content_type:
            self.send_header("Content-type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/weather.json":
            try:
                payload = {"yr": build_forecast(), "netatmo": build_netatmo_summary()}
            except (KeyError, IndexError, TypeError) as e:
                serverLogger.error("Could not build weather.json: %s", e)
                self._send(500)
                return
            self._send(200, "application/json", json.dumps(payload).encode('utf-8'))
        elif self.path == "/image.bmp":
            if os.path.isfile(display.DEFAULT_IMAGE_FILENAME):
                with open(display.DEFAULT_IMAGE_FILENAME, "rb") as f:
                    self._send(200, "image/bmp", f.read())
            else:
                self._send(404)
        else:
            self._send(404)


def main():
    utils.setup_logging()
    serverLogger.info("Starting server...")

    # Netatmo service (also fetches weather, air quality and sunrise data) in a background thread
    threading.Thread(target=netatmo.NetatmoService().run, daemon=True).start()
    serverLogger.info("Netatmo service started.")

    serverLogger.info("Serving at http://0.0.0.0:%d/image.bmp", PORT)
    with socketserver.TCPServer(("", PORT), WeatherHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
