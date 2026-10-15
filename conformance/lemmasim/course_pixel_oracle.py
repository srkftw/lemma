"""Independent host-only pixels for the canonical authored course text region.

This observer never supplies machine state or pixels. Literal 3x5 glyph rows,
12x20 cells and 32x16 clipping follow the selected public text layout.
"""
from check_live_notebook import require, visible_pixels

ROWS = {' ': ('000', '000', '000', '000', '000'),
 '!': ('010', '010', '010', '000', '010'),
 '"': ('101', '101', '000', '000', '000'),
 "'": ('010', '010', '000', '000', '000'),
 '(': ('010', '100', '100', '100', '010'),
 ')': ('010', '001', '001', '001', '010'),
 '*': ('101', '010', '111', '010', '101'),
 '+': ('000', '010', '111', '010', '000'),
 ',': ('000', '000', '000', '010', '100'),
 '-': ('000', '000', '111', '000', '000'),
 '.': ('000', '000', '000', '000', '010'),
 '/': ('001', '001', '010', '100', '100'),
 '0': ('111', '101', '101', '101', '111'),
 '1': ('010', '110', '010', '010', '111'),
 '2': ('111', '001', '111', '100', '111'),
 '3': ('111', '001', '111', '001', '111'),
 '4': ('101', '101', '111', '001', '001'),
 '5': ('111', '100', '111', '001', '111'),
 '6': ('111', '100', '111', '101', '111'),
 '7': ('111', '001', '010', '010', '010'),
 '8': ('111', '101', '111', '101', '111'),
 '9': ('111', '101', '111', '001', '111'),
 ':': ('000', '010', '000', '010', '000'),
 ';': ('000', '010', '000', '010', '100'),
 '<': ('001', '010', '100', '010', '001'),
 '=': ('000', '111', '000', '111', '000'),
 '>': ('100', '010', '001', '010', '100'),
 '?': ('111', '001', '010', '000', '010'),
 'A': ('010', '101', '111', '101', '101'),
 'B': ('110', '101', '110', '101', '110'),
 'C': ('111', '100', '100', '100', '111'),
 'D': ('110', '101', '101', '101', '110'),
 'E': ('111', '100', '110', '100', '111'),
 'F': ('111', '100', '110', '100', '100'),
 'G': ('111', '100', '101', '101', '111'),
 'H': ('101', '101', '111', '101', '101'),
 'I': ('111', '010', '010', '010', '111'),
 'J': ('001', '001', '001', '101', '110'),
 'K': ('101', '101', '110', '101', '101'),
 'L': ('100', '100', '100', '100', '111'),
 'M': ('101', '111', '111', '101', '101'),
 'N': ('101', '111', '111', '111', '101'),
 'O': ('111', '101', '101', '101', '111'),
 'P': ('111', '101', '111', '100', '100'),
 'Q': ('111', '101', '101', '111', '001'),
 'R': ('110', '101', '110', '101', '101'),
 'S': ('111', '100', '111', '001', '111'),
 'T': ('111', '010', '010', '010', '010'),
 'U': ('101', '101', '101', '101', '111'),
 'V': ('101', '101', '101', '101', '010'),
 'W': ('101', '101', '101', '111', '111'),
 'X': ('101', '101', '010', '101', '101'),
 'Y': ('101', '101', '010', '010', '010'),
 'Z': ('111', '001', '010', '100', '111'),
 '_': ('000', '000', '000', '000', '111')}


def course_body_matches(path, text):
    width, height, pixels = visible_pixels(path)
    require((width, height) == (1650, 2200), "canonical controller geometry")
    slots = [" "] * 512
    cursor = 0
    for code in text.encode("ascii"):
        if cursor >= len(slots):
            break
        if code == 10:
            cursor += 32 - cursor % 32
        else:
            slots[cursor] = chr(code).upper()
            cursor += 1
    for y in range(320):
        cell_y, glyph_y = divmod(y, 20)
        for x in range(384):
            cell_x, glyph_x = divmod(x, 12)
            pattern = ROWS.get(slots[cell_y * 32 + cell_x], ROWS["O"])
            black = (glyph_x < 9 and glyph_y < 15 and
                     pattern[glyph_y // 3][glyph_x // 3] == "1")
            at = ((320 + y) * width + 24 + x) * 3
            if pixels[at:at + 3] != bytes([0 if black else 255]) * 3:
                return False
    return True


def label_matches(path, text, x=24, y=132):
    width, height, pixels = visible_pixels(path)
    require(0 <= x and 0 <= y and x + len(text) * 12 <= width and
            y + 15 <= height, "label observer bounds")
    for row in range(15):
        for column in range(len(text) * 12):
            glyph = ROWS.get(text[column // 12].upper())
            require(glyph is not None, "unsupported observer glyph")
            within = column % 12
            black = within < 9 and glyph[row // 3][within // 3] == "1"
            at = ((y + row) * width + x + column) * 3
            if pixels[at:at + 3] != bytes([0 if black else 255]) * 3:
                return False
    return True
