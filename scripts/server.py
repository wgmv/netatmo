import http.server
import socketserver
import json
import threading
import netatmo
import weather
import logging
import os 
import utils

logging.basicConfig()
logging.root.setLevel(logging.INFO)

serverLogger = logging.getLogger("server")


class WeatherHandler(http.server.SimpleHTTPRequestHandler):
    def read_and_process_files(self):
        global weather_data
        weather_data = {}
        # Read weather data
        if os.path.isfile(weather.weather_data_filename):
            yr_data = {}
            yr_data = utils.read_json(weather.weather_data_filename)["properties"]["timeseries"]
            filtered_weather_data = []
            index = 0
            for timeseries in yr_data:
                if len(yr_data) >= 18 and (index == 0 or index == 6 or index == 12 or index == 18):
                    curr_timeseries = {}
                    curr_timeseries["time"] = timeseries["time"]
                    if "next_6_hours" in timeseries["data"]:
                        curr_timeseries["summary"] = timeseries["data"]["next_6_hours"]["summary"]["symbol_code"]
                        curr_timeseries["min_temp"] = timeseries["data"]["next_6_hours"]["details"]["air_temperature_min"]
                        curr_timeseries["max_temp"] = timeseries["data"]["next_6_hours"]["details"]["air_temperature_max"]
                        curr_timeseries["precipitation_amount"] = timeseries["data"]["next_6_hours"]["details"]["precipitation_amount"]
                        curr_timeseries["precipitation_amount_max"] = timeseries["data"]["next_6_hours"]["details"]["precipitation_amount_max"]
                        curr_timeseries["precipitation_amount_min"] = timeseries["data"]["next_6_hours"]["details"]["precipitation_amount_min"]

                    filtered_weather_data.append(curr_timeseries)
                index += 1
            weather_data["yr"] = filtered_weather_data
        else:
            serverLogger.error("No weather data file")
            weather_data = {}
        if os.path.isfile(netatmo.data_filename):
            netatmo_data = utils.read_json(netatmo.data_filename)
            filtered_netatmo_data = netatmo_data["body"]["devices"]
            dashboard_data = [filtered_netatmo_data[0]["dashboard_data"]]
            dashboard_data[0]["module_type"] = "NAMain"

            for device in filtered_netatmo_data[0]["modules"]:
                if "dashboard_data" in device:
                    dashboard_data.append(device["dashboard_data"])
                    dashboard_data[-1]["module_type"] = device["type"]

            weather_data["netatmo"] = {}
            main_unit = dashboard_data[0]
            weather_data["netatmo"]["indoor_temperature"] = main_unit["Temperature"]
            weather_data["netatmo"]["indoor_humidity"] = main_unit["Humidity"]
            for module in dashboard_data[1:]:
                print(module["module_type"])
                if module["module_type"] == "NAModule1":
                    weather_data["netatmo"]["outdoor_temperature"] = module["Temperature"]
                    weather_data["netatmo"]["outdoor_humidity"] = module["Humidity"]
                elif module["module_type"] == "NAModule3":
                    weather_data["netatmo"]["rain"] = module["sum_rain_24"]
                elif module["module_type"] == "NAModule2":
                    weather_data["netatmo"]["wind_strength"] = module["WindStrength"]
                    weather_data["netatmo"]["wind_angle"] = module["WindAngle"]

    def do_GET(self):
        if self.path == "/weather.json":
            self.read_and_process_files()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(weather_data).encode('utf-8'))
        elif self.path == "/image.bmp":
            if os.path.exists("image.bmp"):
                with open("image.bmp", "rb") as f:
                    bmp_data = f.read()
                self.send_response(200)
                self.send_header("Content-type", "image/bmp")
                self.send_header("Content-Length", str(len(bmp_data)))
                self.end_headers()
                self.wfile.write(bmp_data)
        else:
            self.send_response(404)
            self.end_headers()

def main():
    serverLogger.info("Starting server...")

    # Start netatmo service in background thread
    netatmo_thread = threading.Thread(target=netatmo.start_netatmo_service, daemon=True)
    netatmo_thread.start()
    serverLogger.info("Netatmo service started.")

    # Start weather data retrieval in background thread
    weather_thread = threading.Thread(target=weather.startWeatherService, daemon=True)
    weather_thread.start()
    serverLogger.info("Weather service started.")

    # start web server
    PORT = 8000
    serverLogger.info(f"Serving at http://0.0.0.0:{PORT}/image.bmp")
    with socketserver.TCPServer(("", PORT), WeatherHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    main()