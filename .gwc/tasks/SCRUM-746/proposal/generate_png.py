#!/usr/bin/env python3
"""Generate detailed.png from detailed.svg (fallback: raw gradient PNG)."""
import struct, zlib, sys
from pathlib import Path

SVG_PATH = Path(__file__).resolve().parent / "detailed.svg"
PNG_PATH = Path(__file__).resolve().parent / "detailed.png"

def try_cairosvg():
    try:
        import cairosvg
        cairosvg.svg2png(
            url=str(SVG_PATH),
            write_to=str(PNG_PATH),
            output_width=900,
            output_height=650,
        )
        print("PNG generated via cairosvg")
        return True
    except ImportError:
        return False

def make_fallback_png():
    width, height = 900, 650
    sig = b'\x89PNG\r\n\x1a\n'

    # IHDR
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)

    # Build raw pixel data: dark gradient background
    raw_data = bytearray()
    for y in range(height):
        raw_data.append(0)  # filter byte
        for x in range(width):
            # Simple vertical gradient from dark to slightly lighter
            t = y / height
            r = int(15 + t * 10)
            g = int(15 + t * 10)
            b = int(26 + t * 20)
            raw_data.extend(bytes([r, g, b]))

    compressed = zlib.compress(bytes(raw_data))
    idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)

    # IEND
    iend_crc = zlib.crc32(b'IEND') & 0xffffffff
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)

    with open(PNG_PATH, 'wb') as f:
        f.write(sig + ihdr + idat + iend)
    print("PNG generated as fallback (gradient background)")

if __name__ == "__main__":
    if not try_cairosvg():
        make_fallback_png()
    print(f"Output: {PNG_PATH} ({PNG_PATH.stat().st_size} bytes)")
