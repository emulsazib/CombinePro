"""Application icon loading.

Builds a multi-resolution QIcon from the exported icon set in `AppIcons/`.
Registering every size lets Qt pick the crispest bitmap per context (16px title
bar, 128px task switcher, 1024px Retina dock) instead of rescaling one source.

Corners are rounded at load time, so the source PNGs stay untouched.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPainterPath, QPixmap

from app.config import REPO_ROOT

log = logging.getLogger(__name__)

ICON_DIR = REPO_ROOT / "AppIcons" / "Assets.xcassets" / "AppIcon.appiconset"
ICON_SIZES = (16, 32, 64, 128, 256, 512, 1024)

# Corner radius, expressed as 14px at a 64px icon and scaled proportionally so
# every size looks the same. A literal 14px would be near-circular at 16px and
# invisible at 1024px. Tune the radius here; the base stays fixed.
CORNER_RADIUS_PX = 14
CORNER_RADIUS_BASE = 64


def _rounded(pixmap: QPixmap) -> QPixmap:
    """Clip a square icon pixmap to a rounded rectangle (transparent corners)."""
    side = pixmap.width()
    radius = side * CORNER_RADIUS_PX / CORNER_RADIUS_BASE

    out = QPixmap(pixmap.size())
    out.fill(Qt.GlobalColor.transparent)

    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(pixmap.rect()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out


def app_icon() -> QIcon:
    """The CombinePro application icon, or an empty QIcon if assets are missing.

    A missing icon is never fatal — the app starts regardless.
    """
    icon = QIcon()
    loaded = 0
    for size in ICON_SIZES:
        path = ICON_DIR / f"{size}.png"
        if not path.is_file():
            continue
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            log.warning("Could not decode icon %s", path)
            continue
        icon.addPixmap(_rounded(pixmap))
        loaded += 1
    if not loaded:
        log.warning("No application icons found in %s", ICON_DIR)
    return icon
