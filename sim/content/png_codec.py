"""png_codec.py — 最小 PNG 编解码（零依赖；zlib+struct 标准库）。

角色、城镇、高度表和方块图集共用；支持 PNG filter 0-4。
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def read_png_rgba(path: Path, *, allow_rgb: bool = True) -> list[list[tuple[int, int, int, int]]]:
    """读 8-bit 非交错 PNG；RGB 默认补不透明 alpha，角色管线可限制为 RGBA。"""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        msg = f"非 PNG 文件: {path}"
        raise ValueError(msg)
    pos = 8
    width = height = 0
    idat = bytearray()
    bit_depth = 8
    color_type = 6
    allowed_types = (2, 6) if allow_rgb else (6,)
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length  # 4 len + 4 type + data + 4 crc
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
            if bit_depth != 8 or color_type not in allowed_types:
                formats = "RGB/RGBA" if allow_rgb else "RGBA"
                msg = f"仅支持 8-bit {formats}，得到 depth={bit_depth} color={color_type}"
                raise ValueError(msg)
            if chunk[10] != 0:
                msg = "不支持交错 PNG"
                raise ValueError(msg)
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
    bpp = 4 if color_type == 6 else 3
    raw = zlib.decompress(bytes(idat))
    stride = width * bpp
    pixels: list[list[tuple[int, int, int, int]]] = []
    prev = [0] * stride
    p = 0
    for _y in range(height):
        ftype = raw[p]
        p += 1
        line = list(raw[p : p + stride])
        p += stride
        _unfilter_line(line, prev, ftype, bpp)
        prev = line
        if bpp == 4:
            row = [
                (line[x * 4], line[x * 4 + 1], line[x * 4 + 2], line[x * 4 + 3])
                for x in range(width)
            ]
        else:
            row = [(line[x * 3], line[x * 3 + 1], line[x * 3 + 2], 255) for x in range(width)]
        pixels.append(row)
    return pixels


def _unfilter_line(line: list[int], prev: list[int], ftype: int, bpp: int = 4) -> None:
    """PNG filter 还原（type 0-4，原地修改 line）。"""

    def paeth(a: int, b: int, c: int) -> int:
        pp = a + b - c
        pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    for i in range(len(line)):
        x = line[i]
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        if ftype == 1:
            x = (x + a) & 0xFF
        elif ftype == 2:
            x = (x + b) & 0xFF
        elif ftype == 3:
            x = (x + (a + b) // 2) & 0xFF
        elif ftype == 4:
            x = (x + paeth(a, b, c)) & 0xFF
        line[i] = x


def write_png_rgba(
    path: Path, width: int, height: int, pixels: list[list[tuple[int, int, int, int]]]
) -> None:
    """RGBA 像素矩阵 → PNG（filter 0，zlib 压缩）。"""

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter 0
        for x in range(width):
            r, g, b, a = pixels[y][x]
            raw += bytes((r, g, b, a))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
