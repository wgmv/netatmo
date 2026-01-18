import json
import time
import logging

utilsLogger = logging.getLogger(__name__)

def read_json(filename):
    """Read a JSON file to a dict object."""
    with open(filename, 'r') as f:
        try:
            data = json.load(f)
        except json.decoder.JSONDecodeError:
            utilsLogger.warning("read_json() JSONDecodeError", exc_info=1)
            data = dict()
    return data

def write_json(data, filename):
    """Write a dict object to a JSON file."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent = 2)

def timestr(t):
    return time.strftime("%H:%M",time.localtime(t))

def format_time_str(t):
    return t.split("T")[0] + " " + t.split("T")[1][0:5]

def textsize(text, font):
    left, top, right, bottom = font.getbbox(text)
    width, height = int(right - left), int(bottom - top)
    return width, height