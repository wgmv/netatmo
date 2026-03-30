# netatmo

A Raspberry Pi + e-Paper display for your Netatmo weather station, with live forecast, air quality, and sunrise/sunset data.

Credit for the original project: [psauliere/netatmo](https://github.com/psauliere/netatmo)

---

## Features

**Indoor panel**
- Temperature with trend arrow, humidity, CO₂ level

**Outdoor panel**
- Temperature with trend arrow, humidity, rain (24 h), wind speed

**Forecast graph** (24-hour temperature curve)
- Continuous curve normalized against current outdoor temperature
- Weather symbols and temperature labels every 6 hours
- Time markers every 3 hours
- Nighttime bar below the graph showing day/night transitions
- Sunrise ↑, sunset ↓, and total daylight duration label

**Air Quality Index** — via [WAQI](https://waqi.info/)

**Display support**
- Waveshare e-Paper: `epd2in7`, `epd5in83`, `epd5in83_V2`, `epd5in83b_V2`
- File-only mode — writes `image.bmp`, no hardware required

---

## Hardware

- [Raspberry Pi Zero W / Zero WH](https://www.berrybase.de/raspberry-pi-zero-2-wh) (or any Pi)
- [Waveshare 5.83" e-Paper HAT](https://www.waveshare.com/wiki/5.83inch_e-Paper_HAT_(B))

The HAT plugs directly onto the 40-pin GPIO header.

---

## Installation

### 1. Raspberry Pi OS

Flash a microSD card with **Raspberry Pi OS Lite (64-bit)** using [Raspberry Pi Imager](https://www.raspberrypi.com/software/). In the custom settings, set a username/password, configure Wi-Fi (2.4 GHz only), and enable SSH.

After first boot, SSH in and update:

```bash
sudo apt update && sudo apt full-upgrade -y && sudo reboot
```

Install dependencies:

```bash
sudo apt install git fonts-freefont-ttf python3-pil python3-requests
```

### 2. Waveshare e-Paper setup

Enable SPI:

```bash
sudo raspi-config
# Interface Options > SPI > Yes
sudo reboot
```

Install Waveshare Python libraries:

```bash
sudo apt install python3-numpy python3-rpi.gpio python3-spidev
git clone https://github.com/waveshare/e-Paper
```

### 3. Clone this repo

```bash
git clone https://github.com/wgmv/netatmo.git
cd netatmo
```

---

## Configuration

### Netatmo API credentials

1. Find your indoor module's **MAC address** (serial number starting with `70:ee:50:`) — visible in the Netatmo app under *Manage my home → your module → Serial number*.
2. Go to [dev.netatmo.com/apps](https://dev.netatmo.com/apps/), create an app, and note the **client id** and **client secret**.
3. Under *Token generator*, select the `read_station` scope, click **Generate Token**, and authorize the app. Copy the **access token** and **refresh token**.

### config/config.json

```json
{
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "device_id": "70:ee:50:xx:xx:xx",
    "refresh_time": 600,
    "screen_type": null,
    "location": {
        "longitude": 0.0,
        "latitude": 0.0,
        "altitude": 0
    },
    "waqi_token": "your_waqi_token"
}
```

| Key | Description |
|-----|-------------|
| `client_id` / `client_secret` | Netatmo app credentials |
| `device_id` | MAC address of your indoor module |
| `refresh_time` | Seconds between station data updates (min 60, default 600) |
| `screen_type` | Waveshare model name, or `null` for file-only mode |
| `location` | Used for forecast and sunrise API calls — updated automatically from station data |
| `waqi_token` | Optional. Get a free token at [aqicn.org/data-platform/token](https://aqicn.org/data-platform/token/) |

### config/token.json

```json
{
    "access_token": "your_access_token",
    "refresh_token": "your_refresh_token"
}
```

This file is updated automatically when the access token is refreshed (every 3 hours). The initial tokens must be generated manually as described above.

---

## Running

Start the service manually:

```bash
python3 src/netatmo.py
```

Or inside a `tmux` session so it keeps running after you disconnect:

```bash
sudo apt install tmux
tmux new -s netatmo
python3 src/netatmo.py
# Detach: Ctrl+B then D
# Reattach: tmux attach -t netatmo
```

The service:
- Fetches station data every `refresh_time` seconds
- Fetches weather forecast, sunrise/sunset, and air quality data every 60 minutes
- Refreshes the OAuth token automatically when it expires

### Autostart on boot

Edit `/etc/rc.local` and add this line before `exit 0`:

```bash
su -c /home/pi/netatmo/scripts/launcher.sh -l pi
```

After reboot, reattach with `tmux attach -t NETATMO`.

---

## File overview

### Source

| File | Purpose |
|------|---------|
| `src/netatmo.py` | Main loop — orchestrates data fetching and display updates |
| `src/display.py` | Renders the display image using PIL |
| `src/weather.py` | Fetches forecast, air quality, and sunrise/sunset data |
| `src/reader.py` | Netatmo API client and token management |
| `src/formatters.py` | Console output formatting |
| `src/utils.py` | JSON I/O, time formatting, text sizing |

### Data (created automatically)

| File | Content |
|------|---------|
| `data/data.json` | Latest station data from Netatmo API |
| `data/weather_data.json` | Latest 24-hour forecast from Met.no |
| `data/sunrise_data.json` | Sunrise/sunset times for today and tomorrow (UTC) |
| `data/aqi_data.json` | Latest air quality data from WAQI |
| `image.bmp` | Generated display image |

---

## Debugging individual services

Run any service module directly to test it in isolation:

```bash
python3 src/weather.py    # fetches forecast, AQI, and sunrise data; prints debug output
python3 src/reader.py     # fetches station data
python3 src/display.py    # renders image.bmp from existing data files
```

---

## References

### APIs
- [Netatmo Developer Documentation](https://dev.netatmo.com/)
- [Met.no Locationforecast API](https://api.met.no/weatherapi/locationforecast/2.0/documentation)
- [Met.no Sunrise API](https://api.met.no/weatherapi/sunrise/3.0/documentation)
- [WAQI Air Quality API](https://aqicn.org/api/)

### Hardware
- [Waveshare e-Paper Wiki](https://www.waveshare.com/wiki/Main_Page#OLEDs_.2F_LCDs)
- [Waveshare 5.83" e-Paper HAT](https://www.waveshare.com/wiki/5.83inch_e-Paper_HAT)
- [Waveshare GitHub (drivers)](https://github.com/waveshare/e-Paper)

### Related projects
- [psauliere/netatmo](https://github.com/psauliere/netatmo) — original project
- [bkoopman/netatmo-display](https://github.com/bkoopman/netatmo-display)
- [SteinTokvam/netatmo](https://github.com/SteinTokvam/netatmo)
