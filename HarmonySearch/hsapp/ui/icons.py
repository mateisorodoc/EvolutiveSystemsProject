"""A small set of authored SVG icons (24x24 grid, 1.8 stroke), recoloured with the theme."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

_STROKE = 'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'

ICONS = {
    "play": '<path d="M8 5.8v12.4a.8.8 0 0 0 1.2.7l9.6-6.2a.8.8 0 0 0 0-1.4L9.2 5.1A.8.8 0 0 0 8 5.8z" fill="{c}"/>',
    "pause": '<rect x="6.5" y="5" width="3.6" height="14" rx="1" fill="{c}"/><rect x="13.9" y="5" width="3.6" height="14" rx="1" fill="{c}"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2" fill="{c}"/>',
    "step": '<path d="M6 6.3v11.4a.8.8 0 0 0 1.2.7l8.4-5.7a.8.8 0 0 0 0-1.4L7.2 5.6A.8.8 0 0 0 6 6.3z" fill="{c}"/>'
            '<rect x="16.6" y="5.5" width="2.4" height="13" rx="1" fill="{c}"/>',
    "reset": f'<path d="M4.6 12a7.4 7.4 0 1 0 2.3-5.4" {_STROKE}/><path d="M4.4 4.6v4.2h4.2" {_STROKE}/>',
    "record": '<circle cx="12" cy="12" r="6" fill="{c}"/>',
    "shuffle": f'<path d="M4 7.5h3.2c1.9 0 2.9.9 4 2.8l1.6 2.8c1.1 1.9 2.1 2.9 4 2.9H20" {_STROKE}/>'
               f'<path d="M4 16h3.2c1.2 0 2-.4 2.8-1.3M14 8.8c.8-.9 1.6-1.3 2.8-1.3H20" {_STROKE}/>'
               f'<path d="M17.6 5.1 20 7.5l-2.4 2.4M17.6 13.6 20 16l-2.4 2.4" {_STROKE}/>',
    "export": f'<path d="M12 4.5v10.5M7.6 10.6 12 15l4.4-4.4M5 19.5h14" {_STROKE}/>',
    "open": f'<path d="M3.8 7.2c0-1 .8-1.7 1.7-1.7h3.8l2 2h7.2c1 0 1.7.8 1.7 1.7v7.9c0 1-.8 1.7-1.7 1.7H5.5c-1 0-1.7-.8-1.7-1.7z" {_STROKE}/>',
    "compare": f'<path d="M4 19.5h16M5 15.5l4-4.5 3.5 2.8L19 6.5" {_STROKE}/><path d="M5 18l4-2.8 3.5 1.2L19 12" {_STROKE} opacity=".5"/>',
    "listen": f'<path d="M4.5 15v-3a7.5 7.5 0 0 1 15 0v3" {_STROKE}/>'
              '<rect x="3.8" y="13.5" width="4" height="6" rx="1.4" fill="{c}"/><rect x="16.2" y="13.5" width="4" height="6" rx="1.4" fill="{c}"/>',
    "save": f'<path d="M5.5 4.5h10l3 3v11a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1z" {_STROKE}/><path d="M8.5 4.5v4.5h6V4.5M8 19.5v-5h8v5" {_STROKE}/>',
}


def icon(name: str, color: str, size: int = 16) -> QIcon:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{ICONS[name].replace("{c}", color)}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    scale = 3
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, size * scale, size * scale))
    p.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def set_icon(button, name: str, on_ink: bool = False):
    """Give a button an icon that follows the theme (``on_ink`` for primary/checked buttons)."""

    def apply():
        try:
            color = theme.ON_INK if (on_ink or button.isChecked()) else theme.TEXT
            button.setIcon(icon(name, color))
        except RuntimeError:
            pass

    button._icon_name = name
    apply()
    theme.THEME.changed.connect(apply)
    if button.isCheckable():
        button.toggled.connect(lambda _: apply())
    return apply
