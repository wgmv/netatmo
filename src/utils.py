"""Utility functions for JSON handling, time formatting, and text size calculation."""

import json
import time
import logging
from datetime import datetime

utilsLogger = logging.getLogger(__name__)

def read_json(filename):
    """Read a JSON file to a dict object."""
    with open(filename, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.decoder.JSONDecodeError:
            utilsLogger.warning("read_json() JSONDecodeError", exc_info=1)
            data = dict()
    return data

def write_json(data, filename):
    """Write a dict object to a JSON file."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent = 2)

def timestr(t):
    """Convert epoch time to HH:MM string."""
    return time.strftime("%H:%M",time.localtime(t))

def format_time_str(t):
    """Convert ISO time string to 'dd.mm.yyyy hh:mm' format.
    
    Args:
        t: ISO format time string (e.g., '2026-01-24T14:30:00Z')
        
    Returns:
        Formatted date/time string (e.g., '24.01.2026 14:30')
    """
    dt = datetime.fromisoformat(t.replace('Z', '+00:00'))
    return dt.strftime('%d.%m.%Y %H:%M')

def textsize(text, font):
    """Calculate text size (width, height) for given text and font."""
    left, top, right, bottom = font.getbbox(text)
    width, height = int(right - left), int(bottom - top)
    return width, height