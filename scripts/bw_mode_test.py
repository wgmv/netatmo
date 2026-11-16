#!/usr/bin/env python3
"""bw_mode_test.py - EXPERIMENT: drive a black/white/red 5.83" V2 panel in black/white mode.

Shows the last rendered picture (image.bmp) with the fast black/white refresh of the
epd5in83_V2 driver, with the data variants selectable, to find out which combination gives
a correct picture on a 3-color panel. Stop the netatmo service before running it.

    python3 scripts/bw_mode_test.py                    # driver defaults
    python3 scripts/bw_mode_test.py --invert           # picture data inverted
    python3 scripts/bw_mode_test.py --old ones         # "previous picture" memory all 1
    python3 scripts/bw_mode_test.py --invert --old ones
    python3 scripts/bw_mode_test.py --cdi 0x11         # other polarity setting of the controller
"""

import argparse
import os
import sys
import time

from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.realpath(os.getenv('HOME', '.') + '/e-Paper/RaspberryPi_JetsonNano/python/lib')


def send_block(epd, command, data):
    epd.send_command(command)
    if hasattr(epd, 'send_data2'):
        epd.send_data2(data)
    else:
        for value in data:
            epd.send_data(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--image', default=os.path.join(BASE_DIR, 'image.bmp'))
    parser.add_argument('--invert', action='store_true', help='send the picture data inverted')
    parser.add_argument('--old', choices=['none', 'zeros', 'ones', 'same', 'inverse'], default='zeros',
                        help='what to write into the "previous picture" memory (default: zeros)')
    parser.add_argument('--cdi', type=lambda v: int(v, 0), default=None,
                        help='first byte of controller register 0x50, e.g. 0x10 or 0x11 '
                             '(default: leave what the driver sets)')
    args = parser.parse_args()

    if LIB_DIR not in sys.path:
        sys.path.append(LIB_DIR)
    from waveshare_epd import epd5in83_V2

    epd = epd5in83_V2.EPD()
    image = Image.open(args.image).convert('1')
    if image.size != (epd.width, epd.height):
        sys.exit(f"{args.image} is {image.size}, panel needs {(epd.width, epd.height)}")

    white_is_1 = image.tobytes()                       # PIL: bit 1 = white
    black_is_1 = bytes(b ^ 0xFF for b in white_is_1)   # what the driver normally sends
    new = white_is_1 if args.invert else black_is_1
    old = {
        'none': None,
        'zeros': bytes(len(new)),
        'ones': b'\xff' * len(new),
        'same': new,
        'inverse': bytes(b ^ 0xFF for b in new),
    }[args.old]

    print(f"invert={args.invert} old={args.old} cdi={args.cdi}")
    epd.init()
    try:
        if args.cdi is not None:
            epd.send_command(0x50)
            epd.send_data(args.cdi)
            epd.send_data(0x07)
        if old is not None:
            send_block(epd, 0x10, old)
        send_block(epd, 0x13, new)
        start = time.time()
        epd.send_command(0x12)   # refresh
        time.sleep(0.1)
        epd.ReadBusy()
        print(f"refresh took {time.time() - start:.1f} s")
    finally:
        epd.sleep()


if __name__ == '__main__':
    main()
