"""Reusable widgets: rotary Dial, Card, score bars, legend swatches, flow layout and segmented toggles."""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .i18n import I18N, bind, tr
from .icons import set_icon

LEFT_W = 330      # width of the settings column
RIGHT_W = 320     # width of the Harmony Search column


class Dial(QWidget):
    """A rotary knob. Drag up/down (Shift = fine), mouse wheel, arrow keys; double-click resets.

    The knob position is always in [0, 1]; ``to_value``/``to_knob`` map it to the
    physical value (linear, logarithmic, integer or any custom mapping).
    """

    valueChanged = Signal(float)
    released = Signal()

    def __init__(
        self,
        label_key: str,
        lo: float = 0.0,
        hi: float = 1.0,
        value: float = 0.5,
        *,
        scale: str = "lin",
        integer: bool = False,
        decimals: int = 2,
        unit: str = "",
        tip_key: Optional[str] = None,
        fmt: Optional[Callable[[float], str]] = None,
        mapping: Optional[Tuple[Callable[[float], float], Callable[[float], float]]] = None,
        default: Optional[float] = None,
        size: int = 60,
        parent=None,
    ):
        super().__init__(parent)
        self.lo, self.hi = lo, hi
        self.scale = scale
        self.integer = integer
        self.decimals = decimals
        self.unit = unit
        self.fmt = fmt
        self.mapping = mapping
        self.knob_size = size
        self.label_key = label_key
        self.tip_key = tip_key
        self.label = tr(label_key)
        self._interactive = True
        self._hover = False
        self._drag_y = None
        self._drag_pos = 0.0
        self._pos = self.to_knob(value)
        self._default_pos = self.to_knob(default if default is not None else value)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.SizeVerCursor)
        self.setAttribute(Qt.WA_Hover)
        I18N.changed.connect(self._retranslate)
        self._retranslate()

    # ---------------------------------------------------------------- mapping
    def to_value(self, k: float) -> float:
        k = min(1.0, max(0.0, k))
        if self.mapping:
            return self.mapping[0](k)
        if self.scale == "log":
            v = self.lo * (self.hi / self.lo) ** k
        else:
            v = self.lo + (self.hi - self.lo) * k
        return float(round(v)) if self.integer else float(v)

    def to_knob(self, v: float) -> float:
        if self.mapping:
            return min(1.0, max(0.0, self.mapping[1](v)))
        if self.scale == "log":
            v = max(v, self.lo)
            return min(1.0, max(0.0, math.log(v / self.lo) / math.log(self.hi / self.lo)))
        return min(1.0, max(0.0, (v - self.lo) / (self.hi - self.lo))) if self.hi != self.lo else 0.0

    # ------------------------------------------------------------------- API
    def value(self) -> float:
        return self.to_value(self._pos)

    def knob(self) -> float:
        return self._pos

    def setValue(self, v: float, emit: bool = True):
        self.setKnob(self.to_knob(v), emit)

    def setKnob(self, k: float, emit: bool = True):
        k = min(1.0, max(0.0, k))
        old = self.value()
        self._pos = k
        if self.integer:
            self._pos = self.to_knob(self.to_value(k))
        self.update()
        if emit and self.value() != old:
            self.valueChanged.emit(self.value())

    def setInteractive(self, on: bool):
        self._interactive = on
        self.setCursor(Qt.SizeVerCursor if on else Qt.ArrowCursor)
        self.update()

    def text(self) -> str:
        v = self.value()
        if self.fmt:
            return self.fmt(v)
        if self.integer:
            s = f"{int(v)}"
        else:
            s = f"{v:.{self.decimals}f}"
        return f"{s} {self.unit}".strip()

    def _retranslate(self):
        try:
            self.label = tr(self.label_key)
            self.setToolTip(tr(self.tip_key) if self.tip_key else "")
            self.updateGeometry()
            self.update()
        except RuntimeError:
            pass

    # --------------------------------------------------------------- painting
    def sizeHint(self) -> QSize:
        label_w = QFontMetrics(theme.font(theme.FS_CAPTION, 600)).horizontalAdvance(self.label) + 6
        return QSize(max(self.knob_size + 20, label_w), self.knob_size + 38)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def event(self, e):
        if e.type() in (e.Type.HoverEnter, e.Type.HoverLeave):
            self._hover = e.type() == e.Type.HoverEnter
            self.update()
        return super().event(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        enabled = self.isEnabled()
        active = enabled and self._interactive

        # label
        p.setFont(theme.font(theme.FS_CAPTION, 600))
        p.setPen(QColor(theme.MUTED))
        p.drawText(QRectF(0, 0, w, 15), Qt.AlignCenter, self.label)

        # arc: track + value
        s = self.knob_size
        r = QRectF((w - s) / 2 + 3, 18, s - 6, s - 6)
        start_deg, span_deg = 225.0, -270.0
        thick = 4.0 if (self._hover and active) or self._drag_y is not None else 3.0
        p.setPen(QPen(QColor(theme.BORDER), thick, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, int(start_deg * 16), int(span_deg * 16))
        val_col = QColor(theme.INK if enabled else theme.BORDER)
        if enabled and not self._interactive:
            val_col = QColor(theme.MUTED)      # driven by Harmony Search: shown, not editable
        p.setPen(QPen(val_col, thick, Qt.SolidLine, Qt.RoundCap))
        if self._pos > 0.002:
            p.drawArc(r, int(start_deg * 16), int(span_deg * self._pos * 16))

        # knob body + pointer
        inner = r.adjusted(8, 8, -8, -8)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor(theme.CARD_HI))
        p.drawEllipse(inner)
        ang = math.radians(start_deg + span_deg * self._pos)
        c = inner.center()
        rad = inner.width() / 2 - 3
        p.setPen(QPen(QColor(theme.TEXT if enabled else theme.MUTED), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(c.x() + math.cos(ang) * rad * 0.3, c.y() - math.sin(ang) * rad * 0.3),
                   QPointF(c.x() + math.cos(ang) * rad, c.y() - math.sin(ang) * rad))
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.INK), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r.adjusted(-4, -4, 4, 4))

        # value
        p.setFont(theme.font(theme.FS_CAPTION, tabular=True))
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(0, 18 + s - 6 + 2, w, 16), Qt.AlignCenter, self.text())
        p.end()

    # ----------------------------------------------------------- interaction
    def mousePressEvent(self, e):
        if not self._interactive or not self.isEnabled():
            return
        self._drag_y = e.position().y()
        self._drag_pos = self._pos
        self.setFocus()
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag_y is None:
            return
        dy = self._drag_y - e.position().y()
        sens = 1000.0 if e.modifiers() & Qt.ShiftModifier else 180.0
        self.setKnob(self._drag_pos + dy / sens)

    def mouseReleaseEvent(self, e):
        if self._drag_y is not None:
            self._drag_y = None
            self.update()
            self.released.emit()

    def mouseDoubleClickEvent(self, e):
        if self._interactive and self.isEnabled():
            self.setKnob(self._default_pos)
            self.released.emit()

    def _step(self) -> float:
        if self.integer:
            span = abs(self.to_value(1.0) - self.to_value(0.0))
            return 1.0 / max(1.0, span)
        return 0.01

    def wheelEvent(self, e):
        if not self._interactive or not self.isEnabled():
            e.ignore()
            return
        n = 1 if e.angleDelta().y() > 0 else -1
        mult = 0.2 if e.modifiers() & Qt.ShiftModifier else 1.0
        self.setKnob(self._pos + n * self._step() * mult)
        self.released.emit()
        e.accept()

    def keyPressEvent(self, e):
        if not self._interactive:
            return
        if e.key() in (Qt.Key_Up, Qt.Key_Right):
            self.setKnob(self._pos + self._step())
            self.released.emit()
        elif e.key() in (Qt.Key_Down, Qt.Key_Left):
            self.setKnob(self._pos - self._step())
            self.released.emit()
        else:
            super().keyPressEvent(e)


class Card(QFrame):
    """Raised surface with an optional heading."""

    def __init__(self, title_key: Optional[str] = None, parent=None, spacing: int = 10):
        super().__init__(parent)
        self.setObjectName("Card")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(16, 14, 16, 16)
        self.outer.setSpacing(spacing)
        if title_key:
            self.title = QLabel()
            self.title.setObjectName("CardTitle")
            bind(self.title.setText, title_key)
            self.outer.addWidget(self.title)

    def add(self, w):
        self.outer.addWidget(w)
        return w

    def add_layout(self, lay):
        self.outer.addLayout(lay)
        return lay


def dial_grid(dials: List[QWidget], cols: int = 3) -> QGridLayout:
    g = QGridLayout()
    g.setHorizontalSpacing(2)
    g.setVerticalSpacing(8)
    for i, d in enumerate(dials):
        g.addWidget(d, i // cols, i % cols, Qt.AlignCenter)
    return g


def dial_group(title_key: str, dials: List[QWidget]) -> QVBoxLayout:
    """A small labelled row of dials (e.g. the synth's Filter section)."""
    box = QVBoxLayout()
    box.setSpacing(4)
    box.addWidget(tlabel(title_key, "Section"))
    row = QHBoxLayout()
    row.setSpacing(2)
    for d in dials:
        row.addWidget(d, 0, Qt.AlignTop)
    box.addLayout(row)
    return box


def tlabel(key: str, object_name: Optional[str] = None, wrap: bool = False, **kw) -> QLabel:
    lab = QLabel()
    if object_name:
        lab.setObjectName(object_name)
    lab.setWordWrap(wrap)
    bind(lab.setText, key, **kw)
    return lab


def tbutton(key: str, primary: bool = False, checkable: bool = False, tip_key: Optional[str] = None,
            icon: Optional[str] = None) -> QPushButton:
    b = QPushButton()
    if primary:
        b.setObjectName("Primary")
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    bind(b.setText, key)
    if tip_key:
        bind(b.setToolTip, tip_key)
    if icon:
        set_icon(b, icon, on_ink=primary)
    return b


def readout(label_key: str) -> Tuple[QHBoxLayout, QLabel]:
    """A labelled numeric readout: label and value on one baseline."""
    row = QHBoxLayout()
    row.setSpacing(10)
    value = QLabel("–")
    value.setObjectName("Readout")
    value.setFont(theme.font(theme.FS_READOUT, 600, display=True, tabular=True))
    row.addWidget(tlabel(label_key, "Muted"), 0, Qt.AlignBottom)
    row.addWidget(value, 0, Qt.AlignBottom)
    return row, value


class ScoreBars(QWidget):
    """Horizontal bars, one per fitness criterion (value in 0..1).

    Ink bars; a criterion turns red only when it is actually poor (state colour with meaning).
    """

    ROW = 22

    def __init__(self, keys: List[str], key_prefix: str, invert: bool = False, parent=None):
        super().__init__(parent)
        self.keys = keys
        self.prefix = key_prefix
        self.invert = invert          # True: values are errors (lower is better)
        self.values: Dict[str, float] = {k: 0.0 for k in keys}
        self.weights: Dict[str, float] = {k: 1.0 for k in keys}
        self.setMinimumHeight(self.ROW * len(keys))
        I18N.changed.connect(self.update)
        theme.THEME.changed.connect(self.update)

    def set_values(self, values: Dict[str, float], weights: Optional[Dict[str, float]] = None):
        self.values = dict(values)
        if weights:
            self.weights = dict(weights)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        label_w = min(118, int(w * 0.42))
        h = self.ROW
        for i, k in enumerate(self.keys):
            y = i * h
            v = float(self.values.get(k, 0.0))
            wt = self.weights.get(k, 1.0)
            p.setFont(theme.font(theme.FS_CAPTION))
            p.setPen(QColor(theme.MUTED if wt > 0 else theme.BORDER))
            p.drawText(QRectF(0, y, label_w - 8, h), Qt.AlignRight | Qt.AlignVCenter, tr(f"{self.prefix}.{k}"))
            bar = QRectF(label_w, y + h / 2 - 3, w - label_w - 46, 6)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.CARD_HI))
            p.drawRoundedRect(bar, 3, 3)
            frac = min(1.0, v * 5) if self.invert else max(0.0, min(1.0, v))
            poor = (v > 0.08) if self.invert else (v < 0.5)
            col = QColor(theme.BORDER) if wt <= 0 else QColor(theme.ERROR if poor else theme.INK)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), max(6.0, bar.width() * frac), bar.height()), 3, 3)
            p.setFont(theme.font(theme.FS_CAPTION, 600, tabular=True))
            p.setPen(QColor(theme.TEXT if wt > 0 else theme.MUTED))
            txt = f"{v:.3f}" if self.invert else f"{v * 100:.0f}"
            p.drawText(QRectF(w - 42, y, 42, h), Qt.AlignRight | Qt.AlignVCenter, txt)
        p.end()


class Segmented(QWidget):
    """A small segmented control (e.g. EN | RO, Light | Dark)."""

    def __init__(self, options: List[Tuple[str, str]], current: str, on_pick: Callable[[str], None], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.buttons: Dict[str, QPushButton] = {}
        self.on_pick = on_pick
        for code, key in options:
            b = QPushButton()
            bind(b.setText, key)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self._pick(c))
            lay.addWidget(b)
            self.buttons[code] = b
        self.set_current(current)

    def _pick(self, code):
        self.set_current(code)
        self.on_pick(code)

    def set_current(self, code):
        for c, b in self.buttons.items():
            b.setChecked(c == code)


class Chip(QWidget):
    """Legend entry: a painted colour swatch and a label."""

    def __init__(self, color_fn: Callable[[], str], key: str, outlined: bool = False, parent=None):
        super().__init__(parent)
        self.color_fn = color_fn
        self.key = key
        self.outlined = outlined
        I18N.changed.connect(self._changed)
        theme.THEME.changed.connect(self.update)

    def _changed(self):
        try:
            self.updateGeometry()
            self.update()
        except RuntimeError:
            pass

    def sizeHint(self):
        fm = QFontMetrics(theme.font(theme.FS_CAPTION))
        return QSize(18 + fm.horizontalAdvance(tr(self.key)) + 4, max(18, fm.height() + 2))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        sw = QRectF(1, (h - 10) / 2, 10, 10)
        col = QColor(self.color_fn())
        if self.outlined:
            p.setPen(QPen(QColor(theme.INK), 1.2))
            p.setBrush(QColor(theme.CARD))
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(col)
        p.drawRoundedRect(sw, 2.5, 2.5)
        p.setFont(theme.font(theme.FS_CAPTION))
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(18, 0, self.width() - 18, h), Qt.AlignLeft | Qt.AlignVCenter, tr(self.key))
        p.end()


class FlowLayout(QLayout):
    """Lays out children left to right, wrapping to new lines (Qt's flow layout example)."""

    def __init__(self, parent=None, h_spacing=14, v_spacing=6):
        super().__init__(parent)
        self._items = []
        self._h, self._v = h_spacing, v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _do_layout(self, rect, test_only):
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            if it.widget() is not None and it.widget().isHidden():
                continue
            hint = it.sizeHint()
            nx = x + hint.width() + self._h
            if nx - self._h > rect.right() and line_h > 0:
                x = rect.x()
                y += line_h + self._v
                nx = x + hint.width() + self._h
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()
