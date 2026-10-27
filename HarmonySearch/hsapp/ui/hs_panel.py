"""Shared Harmony Search UI: runner, parameter panel, convergence plot, memory table, step view, comparison."""

from __future__ import annotations

import copy
import time
from typing import Callable, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..hs import SRC_ADJUSTED, SRC_BEST, SRC_MEMORY, SRC_RANDOM, HarmonySearch, HSParams, run_to_completion
from . import theme
from .i18n import I18N, bind, tr
from .icons import icon
from .widgets import Card, Chip, Dial, dial_grid, tbutton, tlabel

# A factory returns (variables, objective, maximize) for the current problem.
ProblemFactory = Callable[[], Tuple[list, Callable, bool]]


class ProblemAdapter:
    """How the generic HS views should display the variables of a specific problem."""

    maximize = True
    col_width = 60

    def names(self) -> List[str]:
        raise NotImplementedError

    def cell_text(self, j: int, v: float) -> str:
        return f"{v:.3g}"

    def cell_color(self, j: int, v: float) -> QColor:
        return QColor(theme.CARD)

    def fitness_text(self, f: float) -> str:
        return f"{f:.4f}"


# =============================================================== runner
class HSRunner(QObject):
    """Owns the HarmonySearch engine and drives it from a Qt timer."""

    reset_done = Signal()
    refreshed = Signal()       # throttled: redraw plots/tables
    stepped = Signal()         # a single improvisation that the user should be able to follow
    running_changed = Signal(bool)
    finished = Signal()

    def __init__(self, params: HSParams, parent=None):
        super().__init__(parent)
        self.params = params
        self.factory: Optional[ProblemFactory] = None
        self.engine: Optional[HarmonySearch] = None
        self.speed = 0.0                 # improvisations per second, 0 = as fast as possible
        self.par_hist: List[float] = []
        self.bw_hist: List[float] = []
        self.rate = 0.0
        self._acc = 0.0
        self._last_tick = 0.0
        self._last_refresh = 0.0
        self._rate_t0 = 0.0
        self._rate_n0 = 0
        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._tick)

    @property
    def running(self) -> bool:
        return self.timer.isActive()

    def set_factory(self, factory: ProblemFactory):
        self.factory = factory
        self.reset()

    def reset(self):
        was_running = self.running
        self.pause()
        if self.factory is None:
            return
        variables, objective, maximize = self.factory()
        self.engine = HarmonySearch(variables, objective, self.params, maximize=maximize)
        self.par_hist = [self.params.par_at(0)]
        self.bw_hist = [self.params.bw_at(0)]
        self.reset_done.emit()
        self.refreshed.emit()
        if was_running:
            self.start()

    def start(self):
        if self.engine is None:
            return
        if self.engine.finished:
            self.reset()
        self._last_tick = time.perf_counter()
        self._rate_t0, self._rate_n0 = self._last_tick, self.engine.t
        self._acc = 0.0
        self.timer.start()
        self.running_changed.emit(True)

    def pause(self):
        if self.timer.isActive():
            self.timer.stop()
            self.running_changed.emit(False)
            self.refreshed.emit()

    def toggle(self):
        self.pause() if self.running else self.start()

    def _do_step(self):
        imp = self.engine.step()
        self.par_hist.append(imp.par)
        self.bw_hist.append(imp.bw)

    def step_once(self):
        if self.engine is None:
            return
        self.pause()
        if self.engine.finished:
            return
        self._do_step()
        self.stepped.emit()
        self.refreshed.emit()

    def _tick(self):
        eng = self.engine
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        n_done = 0
        if self.speed <= 0:
            budget = now + 0.03
            while not eng.finished and time.perf_counter() < budget:
                self._do_step()
                n_done += 1
        else:
            self._acc += self.speed * dt
            n = min(int(self._acc), 500)
            self._acc -= n
            for _ in range(n):
                if eng.finished:
                    break
                self._do_step()
                n_done += 1
        if now - self._rate_t0 > 0.5:
            self.rate = (eng.t - self._rate_n0) / (now - self._rate_t0)
            self._rate_t0, self._rate_n0 = now, eng.t
        if n_done and 0 < self.speed <= 30:
            self.stepped.emit()
        if n_done and (now - self._last_refresh > 0.08 or (0 < self.speed <= 30)):
            self._last_refresh = now
            self.refreshed.emit()
        if eng.finished:
            self.pause()
            self.finished.emit()


# =============================================================== parameter panel
VARIANT_KEYS = ("classic", "ihs", "ghs")


class HSPanel(QWidget):
    """Right-hand column: algorithm parameters and run controls."""

    compare_requested = Signal()

    def __init__(self, runner: HSRunner, ni_max: int = 100000, parent=None):
        super().__init__(parent)
        self.runner = runner
        p = runner.params
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # --- algorithm card
        algo = Card("hs.algorithm")
        row = QHBoxLayout()
        row.setSpacing(4)
        self.variant_buttons = {}
        for v in VARIANT_KEYS:
            b = tbutton(f"variant.{v}", checkable=True, tip_key=f"variant.{v}.tip")
            b.clicked.connect(lambda _=False, vv=v: self._set_variant(vv))
            row.addWidget(b)
            self.variant_buttons[v] = b
        algo.add_layout(row)
        self.variant_desc = QLabel()
        self.variant_desc.setObjectName("Muted")
        self.variant_desc.setWordWrap(True)
        algo.add(self.variant_desc)

        self.d_hms = Dial("p.hms", 1, 100, p.hms, integer=True, tip_key="p.hms.tip")
        self.d_hmcr = Dial("p.hmcr", 0, 1, p.hmcr, tip_key="p.hmcr.tip")
        self.d_par = Dial("p.par", 0, 1, p.par, tip_key="p.par.tip")
        self.d_bw = Dial("p.bw", 0.001, 0.5, p.bw, scale="log", decimals=3, tip_key="p.bw.tip")
        self.d_par_min = Dial("p.par_min", 0, 1, p.par_min, tip_key="p.par_min.tip")
        self.d_par_max = Dial("p.par_max", 0, 1, p.par_max, tip_key="p.par_max.tip")
        self.d_bw_min = Dial("p.bw_min", 0.0001, 0.5, p.bw_min, scale="log", decimals=4, tip_key="p.bw_min.tip")
        self.d_bw_max = Dial("p.bw_max", 0.001, 0.5, p.bw_max, scale="log", decimals=3, tip_key="p.bw_max.tip")
        self.d_ni = Dial("p.ni", 50, ni_max, p.ni, scale="log", integer=True, tip_key="p.ni.tip",
                         fmt=lambda v: f"{int(v):,}".replace(",", " "))
        self.param_dials = [self.d_hms, self.d_hmcr, self.d_par, self.d_bw, self.d_par_min, self.d_par_max,
                            self.d_bw_min, self.d_bw_max, self.d_ni]
        self.grid = dial_grid([], 3)
        algo.add_layout(self.grid)
        for d in self.param_dials:
            d.valueChanged.connect(self._params_changed)
        self.d_hms.released.connect(self._hms_released)

        seed_row = QHBoxLayout()
        seed_row.addWidget(tlabel("p.seed", "Muted"))
        self.seed = QLineEdit(str(p.seed) if p.seed else "")
        self.seed.setValidator(QIntValidator(0, 99999, self.seed))
        bind(self.seed.setToolTip, "p.seed.tip")
        bind(self.seed.setPlaceholderText, "p.seed.random")
        self.seed.textChanged.connect(self._seed_changed)
        seed_row.addWidget(self.seed, 1)
        algo.add_layout(seed_row)
        lay.addWidget(algo)

        # --- run card
        run = Card("hs.run")
        brow = QHBoxLayout()
        brow.setSpacing(4)
        self.b_reset = tbutton("btn.reset", tip_key="btn.reset.tip", icon="reset")
        self.b_step = tbutton("btn.step", tip_key="btn.step.tip", icon="step")
        self.b_run = tbutton("btn.run", primary=True, icon="play")
        brow.addWidget(self.b_reset)
        brow.addWidget(self.b_step)
        brow.addWidget(self.b_run, 1)
        run.add_layout(brow)
        self.b_reset.clicked.connect(runner.reset)
        self.b_step.clicked.connect(runner.step_once)
        self.b_run.clicked.connect(runner.toggle)

        srow = QHBoxLayout()
        self.d_speed = Dial("p.speed", 1, 1000, 1000, scale="log", integer=True, tip_key="p.speed.tip",
                            fmt=lambda v: "MAX" if v >= 1000 else f"{v:.0f}/s")
        self.d_speed.valueChanged.connect(self._speed_changed)
        srow.addWidget(self.d_speed)
        info = QVBoxLayout()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        info.addWidget(self.progress)
        info.addWidget(self.status)
        info.addStretch(1)
        srow.addLayout(info, 1)
        run.add_layout(srow)
        self.b_compare = tbutton("btn.compare", tip_key="btn.compare.tip", icon="compare")
        self.b_compare.clicked.connect(self.compare_requested.emit)
        run.add(self.b_compare)
        lay.addWidget(run)

        # --- legend
        legend = Card("hs.legend", spacing=6)
        for src, key in ((SRC_MEMORY, "src.memory"), (SRC_ADJUSTED, "src.adjusted"), (SRC_RANDOM, "src.random"),
                         (SRC_BEST, "src.best")):
            legend.add(Chip(lambda s=src: theme.SOURCE_COLORS[s], key))
        legend.add(tlabel("hs.legend.hint", "Muted", wrap=True))
        lay.addWidget(legend)
        lay.addStretch(1)

        runner.running_changed.connect(self._running_changed)
        runner.refreshed.connect(self.refresh)
        I18N.changed.connect(self._retranslate)
        theme.THEME.changed.connect(lambda: self._running_changed(self.runner.running))
        self._set_variant(p.variant, reset=False)
        self._running_changed(False)

    # ------------------------------------------------------------------
    def _retranslate(self):
        self.variant_desc.setText(tr(f"variant.{self.runner.params.variant}.desc"))
        self._running_changed(self.runner.running)
        self.refresh()

    def _set_variant(self, v, reset=False):
        self.runner.params.variant = v
        for k, b in self.variant_buttons.items():
            b.setChecked(k == v)
        visible = {
            "classic": [self.d_hms, self.d_hmcr, self.d_par, self.d_bw, self.d_ni],
            "ihs": [self.d_hms, self.d_hmcr, self.d_ni, self.d_par_min, self.d_par_max, self.d_bw_min, self.d_bw_max],
            "ghs": [self.d_hms, self.d_hmcr, self.d_ni, self.d_par_min, self.d_par_max],
        }[v]
        while self.grid.count():
            self.grid.takeAt(0)
        for i, d in enumerate(visible):
            self.grid.addWidget(d, i // 3, i % 3, Qt.AlignCenter)
        for d in self.param_dials:
            d.setVisible(d in visible)
        self.variant_desc.setText(tr(f"variant.{v}.desc"))
        if self.runner.engine is not None:
            # GHS precomputes whether variables share one domain; a reset keeps the comparison fair
            self.runner.reset()

    def _params_changed(self, _=None):
        p = self.runner.params
        p.hmcr = self.d_hmcr.value()
        p.par = self.d_par.value()
        p.bw = self.d_bw.value()
        p.par_min = self.d_par_min.value()
        p.par_max = self.d_par_max.value()
        p.bw_min = self.d_bw_min.value()
        p.bw_max = self.d_bw_max.value()
        p.ni = int(self.d_ni.value())
        self.refresh()

    def _hms_released(self):
        hms = int(self.d_hms.value())
        if hms != self.runner.params.hms:
            self.runner.params.hms = hms
            self.runner.reset()

    def _seed_changed(self, text):
        self.runner.params.seed = int(text) if text and int(text) > 0 else None

    def _speed_changed(self, v):
        self.runner.speed = 0.0 if v >= 1000 else float(v)

    def _running_changed(self, running):
        self.b_run.setText(tr("btn.pause") if running else tr("btn.run"))
        self.b_run.setIcon(icon("pause" if running else "play", theme.ON_INK))
        self.d_hms.setInteractive(not running)

    def set_params(self, params: HSParams):
        """Load a parameter preset into the dials."""
        for d, v in ((self.d_hms, params.hms), (self.d_hmcr, params.hmcr), (self.d_par, params.par), (self.d_bw, params.bw),
                     (self.d_par_min, params.par_min), (self.d_par_max, params.par_max), (self.d_bw_min, params.bw_min),
                     (self.d_bw_max, params.bw_max), (self.d_ni, params.ni)):
            d.setValue(v, emit=False)

    def refresh(self):
        eng = self.runner.engine
        if eng is None:
            return
        p = self.runner.params
        self.progress.setMaximum(max(1, p.ni))
        self.progress.setValue(min(eng.t, p.ni))
        rate = f"{self.runner.rate:,.0f}".replace(",", " ") if self.runner.running else "0"
        self.status.setText(tr("hs.status", t=eng.t, ni=p.ni, evals=eng.evaluations, rate=rate,
                               par=p.par_at(eng.t), bw=p.bw_at(eng.t)))


# =============================================================== convergence
class ConvergenceView(pg.GraphicsLayoutWidget):
    def __init__(self, runner: HSRunner, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.plot = self.addPlot(row=0, col=0)
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.addLegend(offset=(-10, 10))
        self.c_worst = self.plot.plot()
        self.c_mean = self.plot.plot()
        self.c_best = self.plot.plot()
        self.fill = pg.FillBetweenItem(self.c_best, self.c_worst)
        self.plot.addItem(self.fill)
        for c in (self.c_best, self.c_mean, self.c_worst):
            c.setClipToView(True)
            c.setDownsampling(auto=True, method="peak")
        self.params_plot = self.addPlot(row=1, col=0)
        self.params_plot.setMaximumHeight(130)
        self.params_plot.getAxis("left").enableAutoSIPrefix(False)
        self.params_plot.setXLink(self.plot)
        self.params_plot.addLegend(offset=(-10, 5))
        self.c_par = self.params_plot.plot()
        self.c_bw = self.params_plot.plot()
        for c in (self.c_par, self.c_bw):
            c.setClipToView(True)
            c.setDownsampling(auto=True, method="peak")
        runner.refreshed.connect(self.refresh)
        runner.reset_done.connect(self._reset_view)
        I18N.changed.connect(self._retranslate)
        theme.THEME.changed.connect(self.restyle)
        self.restyle()
        self._retranslate()

    def restyle(self):
        """PAR and bw both drive pitch adjustment, so they use the 'adjusted' provenance colour."""
        self.setBackground(theme.CARD)
        adj = theme.SOURCE_COLORS[SRC_ADJUSTED]
        self.c_best.setPen(pg.mkPen(theme.INK, width=2.2))
        self.c_mean.setPen(pg.mkPen(theme.MUTED, width=1.2, style=Qt.DashLine))
        self.c_worst.setPen(pg.mkPen(theme.ERROR, width=1.2))
        self.fill.setBrush(pg.mkBrush(theme.qc(theme.INK, 22)))
        self.c_par.setPen(pg.mkPen(adj, width=2))
        self.c_bw.setPen(pg.mkPen(adj, width=2, style=Qt.DashLine))
        theme.style_plot(self.plot)
        theme.style_plot(self.params_plot)

    def _retranslate(self):
        for item, key in ((self.c_best, "conv.best"), (self.c_mean, "conv.mean"), (self.c_worst, "conv.worst")):
            self.plot.legend.removeItem(item)
            self.plot.legend.addItem(item, tr(key))
        for item, key in ((self.c_par, "conv.par"), (self.c_bw, "conv.bw")):
            self.params_plot.legend.removeItem(item)
            self.params_plot.legend.addItem(item, tr(key))
        self.plot.setLabel("left", tr("conv.fitness"))
        self.params_plot.setLabel("bottom", tr("conv.improvisation"))

    def _reset_view(self):
        self.plot.enableAutoRange()
        self.params_plot.enableAutoRange()

    def refresh(self):
        eng = self.runner.engine
        if eng is None or not self.isVisible():
            return
        x = np.arange(len(eng.history_best))
        self.c_best.setData(x, np.array(eng.history_best))
        self.c_mean.setData(x, np.array(eng.history_mean))
        self.c_worst.setData(x, np.array(eng.history_worst))
        xp = np.arange(len(self.runner.par_hist))
        self.c_par.setData(xp, np.array(self.runner.par_hist))
        self.c_bw.setData(xp, np.array(self.runner.bw_hist))

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()


# =============================================================== harmony memory table
class MemoryModel(QAbstractTableModel):
    def __init__(self, runner: HSRunner, adapter: ProblemAdapter):
        super().__init__()
        self.runner = runner
        self.adapter = adapter
        self.order: List[int] = []
        self.sort_by_fitness = False
        self.names: List[str] = []

    def rebuild(self):
        self.beginResetModel()
        eng = self.runner.engine
        self.names = self.adapter.names() if eng is not None else []
        if eng is None:
            self.order = []
        else:
            n = len(eng.memory)
            if self.sort_by_fitness:
                f = eng.fitness if eng.maximize else -eng.fitness
                self.order = list(np.argsort(-f))
            else:
                self.order = list(range(n))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.order)

    def columnCount(self, parent=QModelIndex()):
        return 1 + len(self.names)

    def data(self, idx, role=Qt.DisplayRole):
        eng = self.runner.engine
        if eng is None or not idx.isValid():
            return None
        r = self.order[idx.row()]
        c = idx.column()
        last = eng.last
        if c == 0:
            if role == Qt.DisplayRole:
                return self.adapter.fitness_text(eng.fitness[r])
            if role == Qt.BackgroundRole:
                if last is not None and last.replaced_row == r:
                    return theme.tint(theme.WARNING, 0.28)
                if r == eng.best_index:
                    return theme.tint(theme.SUCCESS, 0.28)
                if r == eng.worst_index:
                    return theme.tint(theme.ERROR, 0.22)
                return QColor(theme.CARD)
            if role == Qt.FontRole:
                return theme.font(theme.FS_CAPTION, 600, tabular=True)
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return None
        j = c - 1
        v = eng.memory[r, j]
        if role == Qt.DisplayRole:
            return self.adapter.cell_text(j, v)
        if role == Qt.BackgroundRole:
            return self.adapter.cell_color(j, v)
        if role == Qt.ForegroundRole:
            return theme.text_on(self.adapter.cell_color(j, v))
        if role == Qt.FontRole:
            return theme.font(theme.FS_CAPTION, tabular=True)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            return f"{self.names[j]} = {self.adapter.cell_text(j, v)}"
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        eng = self.runner.engine
        if role != Qt.DisplayRole or eng is None:
            return None
        if orientation == Qt.Horizontal:
            return tr("hm.fitness") if section == 0 else self.names[section - 1]
        return str(self.order[section] + 1)


class MemoryView(QWidget):
    row_selected = Signal(int)      # memory row index

    def __init__(self, runner: HSRunner, adapter: ProblemAdapter, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.adapter = adapter
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 8, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        self.title = tlabel("hm.title", "CardTitle")
        theme.THEME.changed.connect(self.refresh)
        top.addWidget(self.title)
        top.addStretch(1)
        self.sort = QCheckBox()
        bind(self.sort.setText, "hm.sort")
        self.sort.toggled.connect(self._sort_toggled)
        top.addWidget(self.sort)
        lay.addLayout(top)
        self.model = MemoryModel(runner, adapter)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setDefaultSectionSize(adapter.col_width)
        self.table.horizontalHeader().setMinimumSectionSize(30)
        self.table.clicked.connect(self._clicked)
        lay.addWidget(self.table, 1)
        hint = tlabel("hm.hint", "Muted", wrap=True)
        lay.addWidget(hint)
        runner.refreshed.connect(self.refresh)
        runner.reset_done.connect(self.refresh)
        I18N.changed.connect(self.refresh)

    def _sort_toggled(self, on):
        self.model.sort_by_fitness = on
        self.refresh()

    def _clicked(self, idx):
        if idx.isValid() and idx.row() < len(self.model.order):
            self.row_selected.emit(int(self.model.order[idx.row()]))

    def refresh(self):
        if not self.isVisible():
            return
        sel = self.table.selectionModel().selectedRows()
        self.model.rebuild()
        self.table.setColumnWidth(0, 70)
        if sel:
            self.table.selectRow(sel[0].row())

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()


# =============================================================== step-by-step view
class StepView(QWidget):
    """Explains the last improvisation variable by variable."""

    def __init__(self, runner: HSRunner, adapter: ProblemAdapter, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.adapter = adapter
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 12, 12)
        lay.setSpacing(8)
        lay.addWidget(tlabel("step.title", "CardTitle"))
        theme.THEME.changed.connect(self.refresh)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.summary)
        self.probs = QLabel()
        self.probs.setObjectName("Muted")
        self.probs.setWordWrap(True)
        self.probs.setTextFormat(Qt.RichText)
        lay.addWidget(self.probs)
        self.table = QTableWidget(0, 6)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)
        runner.stepped.connect(self.refresh)
        runner.refreshed.connect(self._maybe_refresh)
        runner.reset_done.connect(self.refresh)
        I18N.changed.connect(self.refresh)
        self._shown_t = -1

    def _maybe_refresh(self):
        eng = self.runner.engine
        if eng is not None and eng.last is not None and eng.last.t != self._shown_t:
            self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    def refresh(self):
        if not self.isVisible():
            return
        eng = self.runner.engine
        self.table.setHorizontalHeaderLabels([tr("step.var"), tr("step.r1"), tr("step.decision"), tr("step.row"),
                                              tr("step.r2"), tr("step.value")])
        p = self.runner.params
        if eng is None or eng.last is None:
            self.summary.setText(tr("step.none"))
            self.probs.setText("")
            self.table.setRowCount(0)
            self._shown_t = -1
            return
        imp = eng.last
        self._shown_t = imp.t
        counts = np.bincount(imp.source, minlength=4)
        if imp.accepted:
            verdict = tr("step.accepted", row=imp.replaced_row + 1)
            color = theme.SUCCESS
        else:
            verdict = tr("step.rejected")
            color = theme.ERROR
        shown = [SRC_MEMORY, SRC_ADJUSTED, SRC_RANDOM] + ([SRC_BEST] if p.variant == "ghs" else [])
        short = {SRC_MEMORY: "src.memory.short", SRC_ADJUSTED: "src.adjusted.short", SRC_RANDOM: "src.random.short",
                 SRC_BEST: "src.best.short"}
        tally = " &nbsp;·&nbsp; ".join(
            f"<b style='color:{theme.SOURCE_COLORS[s]}'>{counts[s]} {tr(short[s])}</b>" for s in shown)
        self.summary.setText(
            tr("step.summary", t=imp.t, f=self.adapter.fitness_text(imp.fitness),
               worst=self.adapter.fitness_text(imp.worst_before))
            + f" <b style='color:{color}'>{verdict}</b><br>" + tally
        )
        hmcr, par = p.hmcr, imp.par
        self.probs.setText(tr("step.probs", hmcr=hmcr, par=par, bw=imp.bw, pm=hmcr * (1 - par), pa=hmcr * par, pr=1 - hmcr))

        names = self.adapter.names()
        n = len(imp.harmony)
        self.table.setRowCount(n)
        dec_key = {SRC_MEMORY: "src.memory.short", SRC_ADJUSTED: "src.adjusted.short", SRC_RANDOM: "src.random.short",
                   SRC_BEST: "src.best.short"}
        for i in range(n):
            src = int(imp.source[i])
            cells = [
                names[i],
                f"{imp.r1[i]:.2f} {'<' if imp.r1[i] < hmcr else '≥'} {hmcr:.2f}",
                tr(dec_key[src]),
                str(imp.row[i] + 1) if imp.row[i] >= 0 else "—",
                (f"{imp.r2[i]:.2f} {'<' if imp.r2[i] < par else '≥'} {par:.2f}") if not np.isnan(imp.r2[i]) else "—",
                (f"{self.adapter.cell_text(i, imp.before_adjust[i])} → " if not np.isnan(imp.before_adjust[i]) else "")
                + self.adapter.cell_text(i, imp.harmony[i]),
            ]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignCenter)
                if c == 2:
                    it.setBackground(theme.tint(theme.SOURCE_COLORS[src], 0.3))
                    it.setForeground(QColor(theme.TEXT))
                    it.setFont(theme.font(theme.FS_CAPTION, 600))
                self.table.setItem(i, c, it)


class MemoryAndStep(QSplitter):
    def __init__(self, runner, adapter, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.memory = MemoryView(runner, adapter)
        self.step = StepView(runner, adapter)
        self.addWidget(self.memory)
        self.addWidget(self.step)
        self.setStretchFactor(0, 3)
        self.setStretchFactor(1, 2)


# =============================================================== variant comparison
class _CompareWorker(QThread):
    progress = Signal(int, int)                 # done, total
    result = Signal(str, object, float)         # variant, curves (runs x ni+1), seconds

    def __init__(self, factory: ProblemFactory, base: HSParams, runs: int, ni: int):
        super().__init__()
        self.factory = factory
        self.base = base
        self.runs = runs
        self.ni = ni
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        variables, objective, maximize = self.factory()
        total = 3 * self.runs * self.ni
        done = 0
        for v in VARIANT_KEYS:
            curves = []
            t0 = time.perf_counter()
            for r in range(self.runs):
                p = copy.copy(self.base)
                p.variant = v
                p.ni = self.ni
                p.seed = 1000 + r              # same seeds for every variant: a fair comparison
                base_done = done

                def prog(t, base_done=base_done):
                    self.progress.emit(base_done + t, total)

                curve, _ = run_to_completion(variables, objective, p, maximize=maximize, progress=prog,
                                             cancelled=lambda: self._cancel)
                if self._cancel:
                    return
                curves.append(curve)
                done += self.ni
            self.result.emit(v, np.array(curves), time.perf_counter() - t0)
        self.progress.emit(total, total)


class CompareDialog(QDialog):
    def __init__(self, factory: ProblemFactory, params: HSParams, adapter: ProblemAdapter, default_ni: int, parent=None):
        super().__init__(parent)
        self.factory = factory
        self.params = params
        self.adapter = adapter
        self.worker: Optional[_CompareWorker] = None
        bind(self.setWindowTitle, "cmp.title")
        self.resize(900, 620)
        lay = QVBoxLayout(self)
        lay.addWidget(tlabel("cmp.desc", "Muted", wrap=True))
        row = QHBoxLayout()
        row.addWidget(tlabel("cmp.runs"))
        self.runs = QSpinBox()
        self.runs.setRange(1, 20)
        self.runs.setValue(3)
        row.addWidget(self.runs)
        row.addSpacing(16)
        row.addWidget(tlabel("cmp.ni"))
        self.ni = QSpinBox()
        self.ni.setRange(50, 200000)
        self.ni.setSingleStep(500)
        self.ni.setValue(default_ni)
        row.addWidget(self.ni)
        row.addStretch(1)
        self.b_start = tbutton("cmp.start", primary=True, icon="play")
        self.b_start.clicked.connect(self.start)
        row.addWidget(self.b_start)
        lay.addLayout(row)
        self.progress = QProgressBar()
        lay.addWidget(self.progress)
        self.plot = pg.PlotWidget(background=theme.CARD)
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.addLegend(offset=(-10, 10))
        theme.style_plot(self.plot.getPlotItem())
        self.plot.setLabel("bottom", tr("conv.improvisation"))
        self.plot.setLabel("left", tr("cmp.best_mean"))
        lay.addWidget(self.plot, 1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("cmp.variant"), tr("cmp.final"), tr("cmp.std"), tr("cmp.time")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(130)
        lay.addWidget(self.table)

    def start(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            return
        self.plot.clear()
        self.table.setRowCount(0)
        self.worker = _CompareWorker(self.factory, self.params, self.runs.value(), self.ni.value())
        self.worker.progress.connect(lambda d, t: (self.progress.setMaximum(t), self.progress.setValue(d)))
        self.worker.result.connect(self._result)
        self.worker.finished.connect(lambda: self.b_start.setText(tr("cmp.start")))
        self.b_start.setText(tr("cmp.cancel"))
        self.worker.start()

    def _result(self, variant, curves, seconds):
        colors = theme.VARIANT_COLORS
        mean = curves.mean(axis=0)
        std = curves.std(axis=0)
        x = np.arange(len(mean))
        col = colors[variant]
        upper = self.plot.plot(x, mean + std, pen=pg.mkPen(theme.qc(col, 0)))
        lower = self.plot.plot(x, mean - std, pen=pg.mkPen(theme.qc(col, 0)))
        self.plot.addItem(pg.FillBetweenItem(upper, lower, brush=pg.mkBrush(theme.qc(col, 40))))
        self.plot.plot(x, mean, pen=pg.mkPen(col, width=2.5), name=tr(f"variant.{variant}"))
        finals = curves[:, -1]
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, text in enumerate([tr(f"variant.{variant}"), self.adapter.fitness_text(finals.mean()),
                                  self.adapter.fitness_text(finals.std()), f"{seconds:.1f} s"]):
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, c, it)

    def closeEvent(self, e):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(e)
