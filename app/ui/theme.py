"""CombinePro design system — "Obsidian Logic".

The single source of truth for the dark, high-density IDE look: deep obsidian
surfaces, a terminal-green primary, logic-blue secondary, **sharp 0px corners**,
**1px `#3b4b3f` borders** (not shadows), Inter + JetBrains Mono, 4px scrollbars.

Every color, font stack, the global Qt Style Sheet and the dark QPalette live
here, so the whole UI reads as one system. Call `apply_theme(app)` once at
startup. Tokens mirror `design/obsidian_logic/DESIGN.md`.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication

# --------------------------------------------------------------------- surfaces
# Deepest → raised. Depth is communicated by tone, never by shadow.
BG_LOWEST = "#0c0e12"     # editor gutter, terminal, deepest wells
BG_BASE = "#111317"       # window + editor background
BG_SURFACE = "#1a1c20"    # sidebars, nav rail, panels
BG_CONTAINER = "#1e2024"  # cards, inputs, chips
BG_RAISED = "#1e2024"     # alias: cards / inputs
BG_HIGH = "#282a2e"       # hover / pressed
BG_HOVER = "#282a2e"
BG_HIGHEST = "#333539"    # selected rows, active wells
BG_BRIGHT = "#37393e"     # tooltips, floating surfaces

# ------------------------------------------------------------------ text / lines
TEXT = "#e2e2e8"          # on-surface
TEXT_MUTED = "#b9cbbc"    # on-surface-variant
TEXT_FAINT = "#849587"    # outline (muted labels, comments)
BORDER = "#3b4b3f"        # outline-variant — every 1px separator
BORDER_STRONG = "#849587" # outline — emphasised separators / focus fallback

# ------------------------------------------------------------------- primary (green)
ACCENT = "#00ff9c"          # primary container — primary buttons, logo
ACCENT_TINT = "#00e38a"     # surface tint — hovers, active green
ACCENT_HOVER = "#00e38a"
ACCENT_PRESSED = "#006d40"  # inverse-primary
ON_ACCENT = "#00391f"       # on-primary (text on green fills)
ACCENT_SOFT = "rgba(0, 227, 138, 0.14)"  # translucent green — selections / glow

# ------------------------------------------------------------- secondary (blue)
SECONDARY = "#adc6ff"
SECONDARY_CONTAINER = "#0566d9"
ON_SECONDARY = "#002e6a"
SECONDARY_SOFT = "rgba(173, 198, 255, 0.14)"

# -------------------------------------------------------------- tertiary (amber)
TERTIARY = "#ffe17a"
TERTIARY_DIM = "#ffdd65"

# ------------------------------------------------------------------- semantic
OK = "#00e38a"       # success / active
WARN = "#ffdd65"     # warning / awake
ERR = "#ffb4ab"      # error
ERR_CONTAINER = "#93000a"
INFO = "#adc6ff"     # info / file deltas
PURPLE = "#ffe17a"   # cross-domain signals (amber, palette has no violet)
TEAL = "#56ffa7"     # memory writes

# ---------------------------------------------- agent identity + live states
# Per-agent accent (thought stream, dots, feed). Harmonised to the palette.
AGENT_COLORS: dict[str, str] = {
    "claude": "#00e38a",   # green
    "openai": "#adc6ff",   # blue
    "gemini": "#ffe17a",   # amber
}
AGENT_FALLBACK = "#b9cbbc"

# Glowing status-dot colors per live agent state.
STATE_COLORS: dict[str, str] = {
    "ACTIVE": "#00e38a",
    "RUNNING": "#adc6ff",
    "IDLE": "#849587",
    "ERROR": "#ffb4ab",
}


def agent_color(name: str) -> str:
    return AGENT_COLORS.get(name, AGENT_FALLBACK)


# Colors handed out to user-added agents, in registration order.
_EXTRA_AGENT_COLORS = ("#56ffa7", "#d8e2ff", "#e4c44f", "#ffb4ab", "#0566d9")


def ensure_agent_color(name: str) -> str:
    """Return the agent's color, assigning a palette color on first sight."""
    if name not in AGENT_COLORS:
        AGENT_COLORS[name] = _EXTRA_AGENT_COLORS[len(AGENT_COLORS) % len(_EXTRA_AGENT_COLORS)]
    return AGENT_COLORS[name]


def state_color(state: str) -> str:
    return STATE_COLORS.get(state.upper(), TEXT_FAINT)


# ----------------------------------------------------------- syntax highlighting
SYN_KEYWORD = "#ffb4ab"    # keyword (red)
SYN_STRING = "#ffe17a"     # string (amber)
SYN_COMMENT = "#849587"    # comment (gray)
SYN_NUMBER = "#adc6ff"     # number (blue)
SYN_DECORATOR = "#ffe17a"  # decorator (amber)
SYN_DEFNAME = "#00e38a"    # func/class name (green)

# Diff highlighting
DIFF_ADD = "#00e38a"
DIFF_DEL = "#ffb4ab"
DIFF_HUNK = "#adc6ff"
DIFF_META = "#849587"

# Code viewer gutter + current line
GUTTER_BG = BG_LOWEST
GUTTER_FG = TEXT_FAINT
# Qt parses an 8-digit hex string as #AARRGGBB (alpha first), so keep alpha in
# the leading byte — a faint overlay for the caret's line.
CURRENT_LINE = "#14ffffff"

# --------------------------------------------------------------------- shape
# DESIGN.md specifies a strictly sharp (0px) shape language. These tokens soften
# it to the subtle radii modern IDEs use (VS Code, Zed, JetBrains) without
# losing the technical, high-density feel. Set all three to "0px" to restore the
# original sharp look — every rounded surface reads from here.
RADIUS = "6px"        # cards, panels, dialogs, menus
RADIUS_SM = "4px"     # buttons, inputs, chips, list rows
RADIUS_PILL = "999px"  # scrollbar handles, status pills

# --------------------------------------------------------------------- fonts
# Inter / JetBrains Mono if installed, else graceful platform fallbacks. No
# download — apply_theme only registers bundled font files if they ever exist.
UI_FONT_STACK = '"Inter", "SF Pro Text", "Segoe UI", "Helvetica Neue", sans-serif'
MONO_FONT_STACK = '"JetBrains Mono", "SF Mono", "Menlo", "Consolas", monospace'


def mono_font(point_size: int = 13) -> QFont:
    """A monospace QFont honoring the JetBrains Mono → Menlo fallback chain."""
    font = QFont()
    font.setFamilies(["JetBrains Mono", "SF Mono", "Menlo", "Consolas"])
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(point_size)
    return font


# ------------------------------------------------------------------ stylesheet

def build_stylesheet() -> str:
    return f"""
    * {{
        font-family: {UI_FONT_STACK};
        font-size: 14px;
        outline: none;
    }}

    QWidget {{
        background-color: {BG_BASE};
        color: {TEXT};
    }}
    QMainWindow, QMainWindow > QWidget {{ background-color: {BG_BASE}; }}
    QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}

    /* =============================== top bar =============================== */
    QToolBar#topbar {{
        background-color: {BG_SURFACE};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 6px 12px;
        spacing: 4px;
    }}
    QToolBar#topbar QLabel {{ background: transparent; }}
    QLabel#logo {{ color: {ACCENT_TINT}; font-size: 15px; font-weight: 700; letter-spacing: -0.01em; }}

    /* top-bar nav tabs (Explorer / Agents / Settings inline) */
    QPushButton[navtab="true"] {{
        background: transparent;
        color: {TEXT_MUTED};
        border: none;
        border-bottom: 2px solid transparent;
        padding: 6px 10px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton[navtab="true"]:hover {{ color: {TEXT}; }}
    QPushButton[navtab="true"][active="true"] {{
        color: {TEXT};
        border-bottom: 2px solid {SECONDARY};
    }}

    /* =============================== buttons ============================== */
    QPushButton {{
        background: {BG_CONTAINER};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        padding: 5px 12px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {BG_HIGH}; border-color: {BORDER_STRONG}; }}
    QPushButton:pressed {{ background: {BG_SURFACE}; }}
    QPushButton:disabled {{ color: {TEXT_FAINT}; border-color: {BORDER}; background: {BG_SURFACE}; }}
    /* Keyboard focus stays visible even though `outline: none` is global. */
    QPushButton:focus {{ border-color: {SECONDARY}; }}
    /* Toolbar buttons carry an icon only, so give them a square tap target. */
    QPushButton[iconOnly="true"] {{ padding: 6px; min-width: 30px; }}

    /* primary (terminal green, black text) */
    QPushButton[variant="primary"] {{
        background: {ACCENT}; color: {ON_ACCENT}; border: 1px solid {ACCENT};
    }}
    QPushButton[variant="primary"]:hover {{ background: {ACCENT_TINT}; border-color: {ACCENT_TINT}; }}
    QPushButton[variant="primary"]:pressed {{ background: {ACCENT_PRESSED}; color: {TEXT}; }}
    QPushButton[variant="primary"]:disabled {{
        background: {BG_HIGH}; color: {TEXT_FAINT}; border-color: {BORDER};
    }}

    /* ghost (1px border, transparent fill) */
    QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid {BORDER}; color: {TEXT_MUTED}; }}
    QPushButton[variant="ghost"]:hover {{ color: {TEXT}; border-color: {BORDER_STRONG}; background: {BG_HIGH}; }}

    /* danger (error container — the Run button while a process is running) */
    QPushButton[variant="danger"] {{
        background: {ERR_CONTAINER}; color: {ERR}; border: 1px solid {ERR};
    }}
    QPushButton[variant="danger"]:hover {{ background: {ERR}; color: {ERR_CONTAINER}; }}
    QPushButton[variant="danger"]:pressed {{ background: {ERR_CONTAINER}; color: {ERR}; }}

    /* =============================== nav sidebar ========================== */
    QFrame#navSidebar {{ background: {BG_SURFACE}; border-right: 1px solid {BORDER}; }}
    QFrame#navSidebar QLabel {{ background: transparent; }}
    QLabel#navBrand {{ color: {ACCENT_TINT}; font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }}
    QLabel#navVersion {{ color: {TEXT_FAINT}; font-size: 11px; font-weight: 600; }}

    QPushButton[nav="true"] {{
        background: transparent;
        color: {TEXT_MUTED};
        border: none;
        border-left: 2px solid transparent;
        border-radius: 0px;
        padding: 8px 12px;
        text-align: left;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton[nav="true"]:hover {{ background: {BG_HIGH}; color: {TEXT}; }}
    QPushButton[nav="true"][active="true"] {{
        background: {BG_HIGHEST};
        color: {ACCENT_TINT};
        border-left: 2px solid {ACCENT_TINT};
        font-weight: 600;
    }}

    /* ============================ section headers ========================= */
    QLabel[caps="true"] {{
        color: {TEXT_FAINT};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.05em;
    }}
    QLabel#h1 {{ color: {TEXT}; font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }}
    QLabel#h2 {{ color: {TEXT}; font-size: 18px; font-weight: 600; letter-spacing: -0.01em; }}
    QLabel[muted="true"] {{ color: {TEXT_MUTED}; font-size: 13px; }}

    /* =============================== cards =============================== */
    QFrame#statCard, QFrame#agentCard, QFrame#panelCard {{
        background: {BG_CONTAINER};
        border: 1px solid {BORDER};
        border-radius: {RADIUS};
    }}
    /* Deactivated agents read as inactive even before the opacity effect. */
    QFrame#agentCard[inactive="true"] {{
        background: {BG_SURFACE};
        border: 1px solid {BORDER};
    }}
    QFrame#statCard QLabel, QFrame#agentCard QLabel, QFrame#panelCard QLabel {{ background: transparent; }}
    QLabel#statValue {{ color: {TEXT}; font-size: 22px; font-weight: 700; }}
    QLabel#agentName {{ color: {TEXT}; font-size: 15px; font-weight: 600; }}

    /* panel header strip (Agent Cluster / AI Thought Stream / etc.) */
    QLabel#panelHeader {{
        background: {BG_SURFACE};
        color: {TEXT_MUTED};
        border-bottom: 1px solid {BORDER};
        padding: 8px 12px;
        font-size: 11px;
        font-weight: 700;
    }}

    /* chips: domain tags, provider tags */
    QLabel[chip="true"] {{
        background: {BG_HIGH};
        color: {TEXT_MUTED};
        border: 1px solid {BORDER};
        padding: 1px 6px;
        font-size: 11px;
        font-weight: 600;
    }}

    /* =============================== file tree =========================== */
    QTreeView {{
        background-color: {BG_SURFACE};
        border: none;
        padding: 4px;
        show-decoration-selected: 1;
        alternate-background-color: {BG_SURFACE};
    }}
    QTreeView::item {{ padding: 4px 6px; border: none; border-radius: {RADIUS_SM}; color: {TEXT_MUTED}; }}
    QTreeView::item:hover {{ background: {BG_HIGH}; color: {TEXT}; }}
    QTreeView::item:selected {{
        background: {SECONDARY_SOFT};
        color: {TEXT};
        border-left: 2px solid {SECONDARY};
    }}

    /* ---- allocation / generic table ---- */
    QTreeWidget {{
        background-color: {BG_CONTAINER};
        border: 1px solid {BORDER};
        border-radius: {RADIUS};
        alternate-background-color: {BG_SURFACE};
        padding: 0px;
    }}
    QTreeWidget::item {{ padding: 6px 8px; border-radius: {RADIUS_SM}; }}
    QTreeWidget::item:selected {{ background: {SECONDARY_SOFT}; color: {TEXT}; }}
    QHeaderView::section {{
        background: {BG_SURFACE};
        color: {TEXT_FAINT};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 6px 8px;
        font-size: 10px;
        font-weight: 700;
    }}

    /* ======================= editors / text areas ======================== */
    QPlainTextEdit {{
        background-color: {BG_BASE};
        color: {TEXT};
        border: none;
        selection-background-color: {SECONDARY_CONTAINER};
        selection-color: {TEXT};
    }}
    QPlainTextEdit#terminal {{
        background-color: {BG_LOWEST};
        border-top: 1px solid {BORDER};
    }}
    QFrame#termInputRow {{ background: {BG_LOWEST}; border-top: 1px solid {BORDER}; }}
    QLineEdit#termInput {{
        background: transparent;
        border: none;
        padding: 2px 0;
        color: {TEXT};
    }}
    QLineEdit#termInput:focus {{ border: none; }}

    /* ============================= prompt bar =========================== */
    QFrame#promptBar {{ background: {BG_SURFACE}; border-top: 1px solid {BORDER}; }}
    QLineEdit#promptInput {{
        background: {BG_LOWEST};
        border: 1px solid {BORDER};
        padding: 8px 12px;
    }}
    QLineEdit#promptInput:focus {{ border: 1px solid {SECONDARY}; }}

    /* =============================== tabs ================================ */
    QTabBar {{ background: {BG_SURFACE}; }}
    QTabBar::tab {{
        background: {BG_SURFACE};
        color: {TEXT_MUTED};
        border: none;
        border-right: 1px solid {BORDER};
        border-top: 2px solid transparent;
        padding: 8px 16px;
        font-size: 13px;
    }}
    QTabBar::tab:hover {{ color: {TEXT}; background: {BG_HIGH}; }}
    QTabBar::tab:selected {{
        background: {BG_BASE};
        color: {TEXT};
        border-top: 2px solid {SECONDARY};
    }}

    /* =============================== inputs ============================== */
    QLineEdit {{
        background: {BG_LOWEST};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        padding: 7px 10px;
        font-family: {MONO_FONT_STACK};
        selection-background-color: {SECONDARY_CONTAINER};
    }}
    QLineEdit:focus {{ border: 1px solid {SECONDARY}; }}
    QLineEdit:disabled {{ color: {TEXT_FAINT}; }}

    QComboBox {{
        background: {BG_CONTAINER};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        padding: 6px 10px;
        min-height: 18px;
    }}
    QComboBox:hover {{ border-color: {BORDER_STRONG}; }}
    QComboBox:focus {{ border-color: {SECONDARY}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {BG_CONTAINER};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS};
        selection-background-color: {SECONDARY_SOFT};
        outline: none;
        padding: 2px;
    }}

    /* ============================== menus =============================== */
    QMenuBar {{ background: {BG_SURFACE}; color: {TEXT_MUTED}; border-bottom: 1px solid {BORDER}; }}
    QMenuBar::item {{ background: transparent; padding: 6px 10px; }}
    QMenuBar::item:selected {{ background: {BG_HIGH}; color: {TEXT}; }}

    /* ============================= status bar =========================== */
    QStatusBar {{
        background: {BG_SURFACE};
        color: {TEXT_MUTED};
        border-top: 1px solid {BORDER};
        font-family: {MONO_FONT_STACK};
        font-size: 11px;
    }}
    QStatusBar::item {{ border: none; }}
    QStatusBar QLabel {{ background: transparent; font-family: {MONO_FONT_STACK}; font-size: 11px; }}

    QLabel#statusPill {{ color: {TEXT_MUTED}; padding: 2px 6px; font-family: {MONO_FONT_STACK}; font-size: 11px; }}
    QLabel#statusPill[healthy="true"] {{ color: {OK}; }}
    QLabel#statusPill[healthy="false"] {{ color: {ERR}; }}

    /* ============================= scrollbars ========================== */
    /* Overlay-style scrollbars: transparent gutter, pill handle that brightens
       on hover. Wider than the original 4px so they're actually grabbable. */
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px 2px 2px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER}; border-radius: {RADIUS_PILL};
        min-height: 32px; margin: 0 2px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {BORDER_STRONG}; }}
    QScrollBar::handle:vertical:pressed {{ background: {ACCENT_TINT}; }}
    QScrollBar:horizontal {{
        background: transparent; height: 10px; margin: 0 2px 2px 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER}; border-radius: {RADIUS_PILL};
        min-width: 32px; margin: 2px 0;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {BORDER_STRONG}; }}
    QScrollBar::handle:horizontal:pressed {{ background: {ACCENT_TINT}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QAbstractScrollArea::corner {{ background: transparent; border: none; }}

    /* ============================== menus ============================== */
    QMenu {{
        background: {BG_BRIGHT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS};
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 24px 7px 12px;
        border-radius: {RADIUS_SM};
        color: {TEXT};
    }}
    QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT_TINT}; }}
    QMenu::item:disabled {{ color: {TEXT_FAINT}; }}
    QMenu::separator {{ height: 1px; background: {BORDER}; margin: 6px 8px; }}
    QMenu::icon {{ padding-left: 8px; }}

    /* ============================= splitter ============================ */
    QSplitter::handle {{ background: {BORDER}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}
    QSplitter::handle:hover {{ background: {SECONDARY}; }}

    QToolTip {{
        background: {BG_BRIGHT};
        color: {TEXT};
        border: 1px solid {BORDER_STRONG};
        border-radius: {RADIUS_SM};
        padding: 6px 10px;
    }}

    /* ============================== dialogs ============================== */
    QDialog {{ background: {BG_BASE}; }}
    QDialog QFrame#panelCard {{ background: {BG_CONTAINER}; }}
    """


def dark_palette() -> QPalette:
    """Base palette so any control the QSS doesn't reach still renders dark."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(BG_BASE))
    p.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Base, QColor(BG_BASE))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_SURFACE))
    p.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Button, QColor(BG_CONTAINER))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_BRIGHT))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Highlight, QColor(SECONDARY_CONTAINER))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_FAINT))
    p.setColor(QPalette.ColorRole.Link, QColor(SECONDARY))
    disabled = QPalette.ColorGroup.Disabled
    p.setColor(disabled, QPalette.ColorRole.Text, QColor(TEXT_FAINT))
    p.setColor(disabled, QPalette.ColorRole.WindowText, QColor(TEXT_FAINT))
    p.setColor(disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_FAINT))
    return p


def _register_bundled_fonts() -> None:
    """Register bundled Inter / JetBrains Mono files if they exist next to this
    module (app/ui/fonts/). No download — silently no-ops if absent, letting the
    platform fallback chain in the font stacks take over."""
    from pathlib import Path

    fonts_dir = Path(__file__).resolve().parent / "fonts"
    if not fonts_dir.is_dir():
        return
    for font_file in fonts_dir.glob("*.[ot]tf"):
        QFontDatabase.addApplicationFont(str(font_file))


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    _register_bundled_fonts()
    font = QFont()
    font.setFamilies(["Inter", "SF Pro Text", "Segoe UI", "Helvetica Neue"])
    font.setPointSize(13)
    app.setFont(font)
    app.setStyleSheet(build_stylesheet())
