"""Utility functions for paths, JSON handling, time formatting, and text size calculation."""

import json
import os
import tempfile
import time
import logging
from datetime import datetime

utilsLogger = logging.getLogger(__name__)

# Project root (parent of src/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")


def setup_logging(level=logging.INFO):
    """Configure root logging once (no-op if already configured)."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')
    root.setLevel(level)


def read_json(filename):
    """Read a JSON file to a dict object."""
    with open(filename, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.decoder.JSONDecodeError:
            utilsLogger.warning("read_json() JSONDecodeError in %s", filename, exc_info=1)
            data = dict()
    return data


def write_json(data, filename):
    """Write a dict object to a JSON file atomically (temp file + rename)."""
    directory = os.path.dirname(os.path.abspath(filename))
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, filename)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def timestr(t):
    """Convert epoch time to HH:MM string."""
    return time.strftime("%H:%M", time.localtime(t))


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
