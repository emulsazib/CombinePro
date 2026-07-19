"""Generate platform icon files from AppIcons/.

Produces `packaging/build/CombinePro.icns` (macOS) and `.ico` (Windows), with
the same proportional corner rounding the in-app icon uses, so the installed
app matches what the running app shows.

The .ico is written by hand — it is just a header, a directory, and embedded
PNGs — which avoids adding Pillow purely as a build dependency.

Run: python packaging/make_icons.py
"""
from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.ui.icons import ICON_DIR, _rounded  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "build"
# Sizes Windows .ico consumers actually use.
ICO_SIZES = (16, 32, 48, 64, 128, 256)
# macOS .iconset requires these exact names.
ICNS_MEMBERS = (
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
)


def rounded_png(size: int, dest: Path) -> None:
    """Render the source icon at `size`, rounded, to `dest`."""
    source = ICON_DIR / f"{size}.png"
    if not source.is_file():  # fall back to the master and downscale
        source = ICON_DIR / "1024.png"
    pixmap = QPixmap(str(source))
    if pixmap.width() != size:
        from PyQt6.QtCore import Qt

        pixmap = pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    _rounded(pixmap).save(str(dest), "PNG")


def build_icns() -> Path | None:
    """macOS .icns via the system iconutil."""
    if sys.platform != "darwin":
        print("• skipping .icns (needs macOS iconutil)")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "CombinePro.iconset"
        iconset.mkdir()
        for name, size in ICNS_MEMBERS:
            rounded_png(size, iconset / name)
        dest = OUT_DIR / "CombinePro.icns"
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(dest)], check=True
        )
    print(f"✓ {dest}  ({dest.stat().st_size:,} bytes)")
    return dest


def build_ico() -> Path:
    """Windows .ico: ICONDIR + ICONDIRENTRY[] + embedded PNG payloads."""
    payloads: list[tuple[int, bytes]] = []
    with tempfile.TemporaryDirectory() as tmp:
        for size in ICO_SIZES:
            png = Path(tmp) / f"{size}.png"
            rounded_png(size, png)
            payloads.append((size, png.read_bytes()))

    dest = OUT_DIR / "CombinePro.ico"
    header = struct.pack("<HHH", 0, 1, len(payloads))  # reserved, type=icon, count
    entries = b""
    offset = len(header) + 16 * len(payloads)
    for size, data in payloads:
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,  # width (0 means 256)
            0 if size >= 256 else size,  # height
            0,      # palette count
            0,      # reserved
            1,      # colour planes
            32,     # bits per pixel
            len(data),
            offset,
        )
        offset += len(data)
    dest.write_bytes(header + entries + b"".join(d for _s, d in payloads))
    print(f"✓ {dest}  ({dest.stat().st_size:,} bytes, {len(payloads)} sizes)")
    return dest


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)  # QPixmap needs a QGuiApplication
    try:
        build_icns()
        build_ico()
    finally:
        app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
