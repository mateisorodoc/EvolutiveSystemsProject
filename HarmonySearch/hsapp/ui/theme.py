"""Design tokens, light/dark palettes, fonts and the global Qt stylesheet.

Design direction (Impeccable, "Operate" surface):
* Neutral surfaces; near-black "ink" carries actions, selection and dial values.
* State colours (success / warning / error) appear only where they mean something.
* Signature move: four colour-blind-safe "provenance" colours (Okabe-Ito) that mark where
  every value of a harmony came from - memory, pitch adjustment, random, global best.
* Light is the default (classrooms and projectors); dark is composed separately, not inverted.

Every module reads tokens as ``theme.NAME`` at use time, so ``apply()`` re-themes live.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase

LIGHT = {
    "BG": "#EDEFF2",        # canvas
    "CARD": "#FFFFFF",      # raised surface
    "PANEL": "#F7F8FA",     # sunken surface: plots, tables
    "CARD_HI": "#E9ECF0",   # controls: buttons, inputs
    "HOVER": "#DFE3E9",
    "BORDER": "#D4D8DF",
    "GRID": "#E4E7EC",
    "TEXT": "#15171C",
    "MUTED": "#565D6B",     # 6.6:1 on white
    "INK": "#15171C",       # primary action fill, dial value arcs
    "ON_INK": "#FFFFFF",
    "SELECT": "#D9E3F2",
    "SUCCESS": "#18794E",
    "WARNING": "#B25E09",
    "ERROR": "#B42318",
    "HEAT_LO": "#EEF1F5",
    "HEAT_HI": "#38465E",
}

DARK = {
    "BG": "#0F1115",
    "CARD": "#171A20",
    "PANEL": "#13161B",
    "CARD_HI": "#222630",
    "HOVER": "#2A2F3A",
    "BORDER": "#2D323D",
    "GRID": "#232731",
    "TEXT": "#ECEEF2",
    "MUTED": "#A2A9B6",     # 7:1 on CARD
    "INK": "#ECEEF2",
    "ON_INK": "#111317",
    "SELECT": "#2B3546",
    "SUCCESS": "#4CC38A",
    "WARNING": "#F0A94B",
    "ERROR": "#F2726B",
    "HEAT_LO": "#1D2129",
    "HEAT_HI": "#7D8FB3",
}

# Provenance of a value: 0 random, 1 memory, 2 memory + pitch adjustment, 3 global best (GHS)
SOURCES_LIGHT = {0: "#B4558E", 1: "#0072B2", 2: "#D55E00", 3: "#009E73"}
SOURCES_DARK = {0: "#DE8FC0", 1: "#56B4E9", 2: "#F08A3C", 3: "#2BC79A"}

# Harmonic role of a melody note: one ink ramp (no extra hues) + error red for "outside"
# 0 chord tone, 1 tension, 2 scale tone, 3 approach (outlined), 4 outside
ROLES_LIGHT = {0: "#1F2633", 1: "#5A6476", 2: "#A9B1BE", 3: "#FFFFFF", 4: "#B42318"}
ROLES_DARK = {0: "#E6E9EF", 1: "#A3ABB9", 2: "#5D6575", 3: "#171A20", 4: "#F2726B"}

VARIANTS_LIGHT = {"classic": "#15171C", "ihs": "#B7791F", "ghs": "#009E73"}
VARIANTS_DARK = {"classic": "#ECEEF2", "ihs": "#F0B44B", "ghs": "#2BC79A"}

NAME = "light"
SOURCE_COLORS = dict(SOURCES_LIGHT)
ROLE_COLORS = dict(ROLES_LIGHT)
VARIANT_COLORS = dict(VARIANTS_LIGHT)
globals().update(LIGHT)

# Type scale (px) and weights
FS_CAPTION, FS_BODY, FS_HEADING, FS_TITLE, FS_READOUT = 12, 13, 15, 20, 28


class _ThemeSignals(QObject):
    changed = Signal()


THEME = _ThemeSignals()


def apply(name: str):
    """Switch palette ('light' or 'dark'). Call ``stylesheet()`` again and emit THEME.changed."""
    global NAME, SOURCE_COLORS, ROLE_COLORS, VARIANT_COLORS
    NAME = name
    dark = name == "dark"
    globals().update(DARK if dark else LIGHT)
    SOURCE_COLORS = dict(SOURCES_DARK if dark else SOURCES_LIGHT)
    ROLE_COLORS = dict(ROLES_DARK if dark else ROLES_LIGHT)
    VARIANT_COLORS = dict(VARIANTS_DARK if dark else VARIANTS_LIGHT)


# ------------------------------------------------------------------ colour helpers
def qc(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


def lerp_color(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(
        int(ca.red() + (cb.red() - ca.red()) * t),
        int(ca.green() + (cb.green() - ca.green()) * t),
        int(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


def heat(t: float) -> QColor:
    """Sequential ramp used for values in the harmony memory table."""
    return lerp_color(HEAT_LO, HEAT_HI, t)


def text_on(bg: QColor) -> QColor:
    """Readable text colour (ink or white) for a given background."""
    lum = 0.2126 * bg.redF() + 0.7152 * bg.greenF() + 0.0722 * bg.blueF()
    return QColor("#15171C") if lum > 0.5 else QColor("#FFFFFF")


def tint(hex_color: str, amount: float = 0.18) -> QColor:
    """Opaque tint of a colour over the card surface (contrast stays predictable)."""
    return lerp_color(CARD, hex_color, amount)


# ------------------------------------------------------------------ fonts
def _family(candidates):
    have = set(QFontDatabase.families())
    for f in candidates:
        if f in have:
            return f
    return None


def ui_family() -> str | None:
    if sys.platform == "win32":
        return _family(["Segoe UI Variable Text", "Segoe UI"])
    return None  # macOS / Linux: the platform UI font (SF Pro on macOS)


def display_family() -> str | None:
    if sys.platform == "win32":
        return _family(["Segoe UI Variable Display", "Segoe UI"])
    return None


def font(px: int, weight: int = 400, display: bool = False, tabular: bool = False, base: QFont | None = None) -> QFont:
    f = QFont(base) if base is not None else QFont()
    fam = display_family() if display else ui_family()
    if fam:
        f.setFamily(fam)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    if tabular:
        try:
            f.setFeature(QFont.Tag("tnum"), 1)
        except Exception:
            pass
    return f


def _css_family(display=False) -> str:
    fam = display_family() if display else ui_family()
    return f"font-family: '{fam}';" if fam else ""


# ------------------------------------------------------------------ pyqtgraph
def style_plot(plot_item, legend: bool = True):
    import pyqtgraph as pg

    for name in ("left", "bottom"):
        ax = plot_item.getAxis(name)
        ax.setPen(pg.mkPen(BORDER))
        ax.setTextPen(pg.mkPen(MUTED))
        ax.setStyle(tickFont=font(FS_CAPTION, tabular=True))
        try:
            ax.label.setDefaultTextColor(QColor(MUTED))
        except Exception:
            pass
    plot_item.showGrid(x=True, y=True, alpha=0.35 if NAME == "light" else 0.25)
    if legend and plot_item.legend is not None:
        plot_item.legend.setBrush(pg.mkBrush(qc(CARD, 235)))
        plot_item.legend.setPen(pg.mkPen(BORDER))
        plot_item.legend.setLabelTextColor(TEXT)


# ------------------------------------------------------------------ stylesheet
def _chevron_url(direction: str = "down") -> str:
    """Write a themed chevron SVG to the temp folder (Qt stylesheets can only load images from files)."""
    import os
    import tempfile

    folder = os.path.join(tempfile.gettempdir(), "harmony_search_studio")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"chevron_{direction}_{MUTED.lstrip('#')}.svg")
    d = "M6.5 9.5 12 15l5.5-5.5" if direction == "down" else "M6.5 14.5 12 9l5.5 5.5"
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{d}" '
                    f'fill="none" stroke="{MUTED}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return path.replace("\\", "/")


def stylesheet() -> str:
    chevron, chevron_up = _chevron_url("down"), _chevron_url("up")
    return f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: {FS_BODY}px; {_css_family()} }}
QToolTip {{ background: {INK}; color: {ON_INK}; border: none; padding: 6px 8px; border-radius: 6px; font-size: {FS_CAPTION}px; }}

QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#Card QLabel, QFrame#Card QCheckBox {{ background: transparent; }}
QLabel#CardTitle {{ color: {TEXT}; font-size: {FS_HEADING}px; font-weight: 600; }}
QLabel#Section {{ color: {MUTED}; font-size: {FS_CAPTION}px; font-weight: 600; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Readout {{ font-size: {FS_READOUT}px; font-weight: 600; {_css_family(True)} }}
QLabel#Title {{ font-size: {FS_TITLE}px; font-weight: 600; {_css_family(True)} }}
QLabel#Subtitle {{ color: {MUTED}; }}

QPushButton {{ background: {CARD_HI}; color: {TEXT}; border: 1px solid transparent; border-radius: 8px;
              padding: 6px 12px; min-height: 18px; font-weight: 600; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:focus {{ border: 1px solid {INK}; }}
QPushButton:disabled {{ color: {MUTED}; background: {PANEL}; }}
QPushButton#Primary, QPushButton:checked {{ background: {INK}; color: {ON_INK}; font-weight: 600; }}
QPushButton#Primary:hover, QPushButton:checked:hover {{ background: {MUTED}; }}
QPushButton#Primary:focus, QPushButton:checked:focus {{ border: 1px solid {BORDER}; }}

QComboBox, QSpinBox, QLineEdit {{ background: {CARD_HI}; border: 1px solid transparent; border-radius: 8px; padding: 4px 8px; min-height: 22px; }}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ background: {HOVER}; }}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border: 1px solid {INK}; }}
QSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 20px; border: none; background: transparent; }}
QSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-arrow {{ image: url("{chevron_up}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{chevron}"); width: 10px; height: 10px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; background: transparent; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER}; selection-background-color: {SELECT}; selection-color: {TEXT}; outline: none; }}
QCheckBox {{ spacing: 8px; }}

QTabWidget#Main::pane {{ border: none; border-top: 1px solid {BORDER}; }}
QTabWidget#Panel::pane {{ border: 1px solid {BORDER}; border-radius: 12px; top: -1px; background: {CARD}; }}
QTabWidget#Panel QWidget {{ background: {CARD}; }}
QTabWidget#Panel QTableView, QTabWidget#Panel QTableWidget {{ background: {CARD}; }}
QTabWidget#Panel QHeaderView::section {{ background: {PANEL}; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 14px; border: none; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {INK}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 3px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}

QTableView, QTableWidget {{ background: {CARD}; alternate-background-color: {PANEL}; gridline-color: {GRID}; border: 1px solid {BORDER};
                           border-radius: 8px; font-size: {FS_CAPTION}px; selection-background-color: {SELECT}; selection-color: {TEXT}; }}
QHeaderView {{ background: {PANEL}; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; border-right: 1px solid {GRID}; border-bottom: 1px solid {GRID};
                        padding: 4px 6px; font-size: {FS_CAPTION}px; font-weight: 600; }}
QTableCornerButton::section {{ background: {PANEL}; border: none; }}
QSplitter::handle {{ background: transparent; }}
QProgressBar {{ background: {CARD_HI}; border: none; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: {INK}; border-radius: 3px; }}
QTextBrowser {{ background: {CARD}; border: none; }}
QDialog {{ background: {BG}; }}
"""
