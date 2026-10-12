"""Literal controller-pixel expectations; never part of a machine adapter.

This observer generates expected empty-notebook bytes solely for comparisons.
No output enters guest memory, device input, media or controller presentation.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from lemmasim_readonly import FONT_ROWS

TOOLS = (
    ('101', '101', '111', '101', '101'),
    ('010', '100', '111', '100', '010'),
    ('010', '001', '111', '001', '010'),
    ('101', '101', '101', '101', '111'),
    ('110', '101', '110', '101', '101'),
    ('111', '100', '110', '100', '111'),
    ('101', '101', '101', '111', '111'),
    ('111', '100', '111', '001', '111'),
    ('111', '100', '100', '100', '111'),
)


def empty_pixels(width, height, status='SAVED', namespace=1, page=1, brush=2):
    if not 512 <= width <= 4096 or not 320 <= height <= 4096:
        raise ValueError('unsupported notebook geometry')
    if status not in ('SAVED', 'PENDING', 'FAILED', 'READ ONLY'):
        raise ValueError('unknown displayed durability state')
    if not 1 <= namespace <= 2 or not 1 <= page <= 64 or brush not in (2, 4, 6):
        raise ValueError('unsupported displayed document identity')
    image = bytearray([255]) * (width * height)

    def rectangle(x, y, w, h, gray):
        x1, y1 = min(width, x+w), min(height, y+h)
        for row in range(y, y1):
            image[row*width+x:row*width+x1] = bytes([gray]) * (x1-x)

    # Literal ruled paper, margin columns and the divider's precedence.
    for y in range(180, height, 96):
        rectangle(0, y, width, 1, 221)
    rectangle(24, 128, 1, height-128, 204)
    rectangle(width-25, 128, 1, height-128, 204)
    rectangle(0, 148, width, 1, 0)
    button = width // 9
    for x in range(0, width, button):
        rectangle(x, 0, min(3, width-x), 128, 0)
        if x+button-3 < width:
            rectangle(x+button-3, 0, min(3, width-(x+button-3)), 128, 0)
    rectangle(0, 0, width, 3, 0)
    rectangle(0, 125, width, 3, 0)
    for index, rows in enumerate(TOOLS):
        for row, pattern in enumerate(rows):
            for column, bit in enumerate(pattern):
                if bit == '1':
                    start = index*button+24+column*12
                    length = min(12, (index+1)*button-start)
                    if length > 0:
                        rectangle(start, 36+row*12, length, 12, 0)

    # The complete fixed footer replaces the margin within its owned box.
    rectangle(24, 132, 336, 16, 255)
    text = f'{status:<9} N{namespace} P{page:02} W{brush}   COURSE'
    if len(text) != 28:
        raise ValueError('footer cells exceed the declared document bounds')
    for index, char in enumerate(text):
        bits = FONT_ROWS.get(char, '0'*15)
        for row in range(5):
            for column in range(3):
                if bits[row*3+column] == '1':
                    rectangle(24+index*12+column*3, 132+row*3, 3, 3, 0)
    return bytes(channel for gray in image for channel in (gray, gray, gray))


def check_empty(width, height, pixels, **displayed):
    expected = empty_pixels(width, height, **displayed)
    if pixels != expected:
        first = next((i for i, (a, b) in enumerate(zip(pixels, expected)) if a != b), None)
        raise ValueError('complete empty-notebook controller pixels differ at byte '+str(first))
    return {'pixels': width*height, 'bytes': len(expected), **displayed}
