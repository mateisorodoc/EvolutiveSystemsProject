"""Tab 1: compose a jazz melody over a chord progression with Harmony Search."""

from __future__ import annotations

import copy
from typing import List, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..hs import HSParams
from ..music import backing as backing_mod
from ..music import composer, midi, render, theory
from ..music.composer import CRITERIA, DEFAULT_WEIGHTS, SLOTS_PER_BAR, MelodyProblem
from ..audio.io import Player, save_wav
from . import theme
from .hs_panel import CompareDialog, ConvergenceView, HSPanel, HSRunner, MemoryAndStep, ProblemAdapter
from .i18n import I18N, bind, tr
from .widgets import LEFT_W, RIGHT_W, Card, Chip, Dial, FlowLayout, ScoreBars, dial_grid, readout, tbutton, tlabel


def note_fmt(v: float) -> str:
    return theory.note_name(int(v))


class JazzAdapter(ProblemAdapter):
    maximize = True
    col_width = 40

    def __init__(self, tab: "JazzTab"):
        self.tab = tab

    def names(self):
        p = self.tab.problem
        return [p.slot_name(i) for i in range(p.n_slots)]

    def cell_text(self, j, v):
        return self.tab.problem.token_label(v)

    def cell_color(self, j, v):
        p = self.tab.problem
        v = int(v)
        if v == p.REST:
            return QColor(theme.CARD)
        if v == p.HOLD:
            return QColor(theme.PANEL)
        return theme.heat(0.15 + 0.85 * v / max(1, p.P - 1))

    def fitness_text(self, f):
        return f"{f * 100:.1f}"


# =================================================================== piano roll
class PianoRoll(QWidget):
    """Draws chords, melody notes (coloured by harmonic role or HS origin) and a playhead."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.problem: Optional[MelodyProblem] = None
        self.notes: List[composer.Note] = []
        self.colors: List[str] = []
        self.strip: Optional[np.ndarray] = None      # per-slot HS source (last improvisation)
        self.playhead: Optional[float] = None         # in slots
        self.setMinimumHeight(260)
        self.setMouseTracking(True)

    def set_data(self, problem, notes, colors, strip=None):
        self.problem, self.notes, self.colors, self.strip = problem, notes, colors, strip
        self.update()

    def set_playhead(self, slot: Optional[float]):
        self.playhead = slot
        self.update()

    def _geom(self):
        p = self.problem
        left, top = 46, 28
        bottom = 16 if self.strip is not None else 4
        w = self.width() - left - 6
        h = self.height() - top - bottom
        rows = p.high - p.low + 1
        return left, top, w / p.n_slots, h / rows, rows

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.CARD))
        p = self.problem
        if p is None:
            return
        left, top, sw, rh, rows = self._geom()
        small = theme.font(theme.FS_CAPTION, tabular=True)
        painter.setFont(small)

        # pitch rows (black keys on the sunken surface) + labels on every C
        for r in range(rows):
            pitch = p.high - r
            y = top + r * rh
            black = (pitch % 12) in (1, 3, 6, 8, 10)
            painter.fillRect(QRectF(left, y, sw * p.n_slots, rh), QColor(theme.PANEL if black else theme.CARD))
            if pitch % 12 == 0 or rh >= 12:
                painter.setPen(QColor(theme.TEXT if pitch % 12 == 0 else theme.MUTED))
                painter.drawText(QRectF(0, y - 2, left - 8, rh + 4), Qt.AlignRight | Qt.AlignVCenter, theory.note_name(pitch))

        # chord-tone rows (quiet ink tint) and chord symbols
        s = 0
        chord_font = theme.font(theme.FS_BODY, 600)
        for ch in p.chords:
            n = ch.beats * 2
            x0 = left + s * sw
            tones = ch.tone_pcs()
            for r in range(rows):
                if (p.high - r) % 12 in tones:
                    painter.fillRect(QRectF(x0, top + r * rh, n * sw, rh), theme.qc(theme.INK, 16))
            painter.setFont(chord_font)
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(QRectF(x0 + 4, 0, n * sw, top - 6), Qt.AlignLeft | Qt.AlignVCenter, ch.symbol)
            s += n
        painter.setFont(small)

        # grid: bars stronger than beats
        for i in range(p.n_slots + 1):
            x = left + i * sw
            if i % SLOTS_PER_BAR == 0:
                painter.setPen(QPen(QColor(theme.BORDER), 1.2))
            elif i % 2 == 0:
                painter.setPen(QPen(QColor(theme.GRID), 1))
            else:
                continue
            painter.drawLine(QPointF(x, top), QPointF(x, top + rows * rh))

        # notes (approach notes are outlined, everything else filled)
        outline = theme.ROLE_COLORS[3]
        for nt, col in zip(self.notes, self.colors):
            r = p.high - nt.pitch
            rect = QRectF(left + nt.start * sw + 1, top + r * rh + 1, nt.length * sw - 2, max(3.0, rh - 2))
            fill = QColor(col)
            painter.setPen(QPen(QColor(theme.INK), 1.3) if col == outline else Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 3, 3)
            if rect.width() > 24 and rh >= 11:
                painter.setPen(QColor(theme.TEXT) if col == outline else theme.text_on(fill))
                painter.drawText(rect, Qt.AlignCenter, theory.NOTE_NAMES[nt.pitch % 12])

        # provenance strip: one cell per decision variable of the last improvisation
        if self.strip is not None:
            y = top + rows * rh + 5
            for i, src in enumerate(self.strip):
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(theme.SOURCE_COLORS[int(src)]))
                painter.drawRoundedRect(QRectF(left + i * sw + 0.75, y, sw - 1.5, 8), 1.5, 1.5)

        if self.playhead is not None:
            x = left + self.playhead * sw
            painter.setPen(QPen(QColor(theme.INK), 1.6))
            painter.drawLine(QPointF(x, top - 2), QPointF(x, top + rows * rh))
        painter.end()


# =================================================================== tab
class JazzTab(QWidget):
    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self.player = player
        self.params = HSParams(variant="classic", hms=30, hmcr=0.95, par=0.3, bw=0.05, par_min=0.1, par_max=0.6,
                               bw_min=0.01, bw_max=0.2, ni=20000)
        self.runner = HSRunner(self.params, self)
        self.adapter = JazzAdapter(self)
        self.selected_row: Optional[int] = None
        self.problem: Optional[MelodyProblem] = None
        self.backing = []
        self._legend_sources = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(16)
        root.addWidget(self._build_left())
        root.addWidget(self._build_center(), 1)
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFixedWidth(RIGHT_W)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hs_panel = HSPanel(self.runner, ni_max=200000)
        self.hs_panel.compare_requested.connect(self._compare)
        right.setWidget(self.hs_panel)
        root.addWidget(right)

        self.runner.refreshed.connect(self.update_display)
        self.runner.reset_done.connect(self._on_reset)
        I18N.changed.connect(self._retranslate)
        theme.THEME.changed.connect(self.update_display)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(30)
        self.play_timer.timeout.connect(self._update_playhead)
        self._rebuild_problem()

    # ------------------------------------------------------------- left column
    def _build_left(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(LEFT_W)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)

        song = Card("jz.song")
        self.prog = QComboBox()
        self.prog.addItems(list(theory.PROGRESSIONS))
        self.prog.currentTextChanged.connect(self._progression_changed)
        self.key = QComboBox()
        self.key.addItems(theory.NOTE_NAMES)
        self.key.setCurrentIndex(theory.PROGRESSIONS[self.prog.currentText()]["default_key"])
        self.key.currentIndexChanged.connect(lambda _: self._rebuild_problem())
        row = QHBoxLayout()
        row.addWidget(self.prog, 3)
        row.addWidget(self.key, 1)
        song.add(tlabel("jz.progression", "Muted"))
        song.add_layout(row)
        self.d_choruses = Dial("jz.choruses", 1, 3, 1, integer=True, tip_key="jz.choruses.tip")
        self.d_tempo = Dial("jz.tempo", 60, 300, 140, integer=True, unit="bpm", tip_key="jz.tempo.tip")
        self.d_swing = Dial("jz.swing", 0.5, 0.75, 0.62, tip_key="jz.swing.tip",
                            fmt=lambda v: f"{v / (1 - v):.1f} : 1")
        self.d_choruses.released.connect(self._rebuild_problem)
        song.add_layout(dial_grid([self.d_choruses, self.d_tempo, self.d_swing], 3))
        lay.addWidget(song)

        mel = Card("jz.melody")
        self.d_low = Dial("jz.low", 40, 79, 60, integer=True, fmt=note_fmt, tip_key="jz.range.tip")
        self.d_high = Dial("jz.high", 55, 96, 81, integer=True, fmt=note_fmt, tip_key="jz.range.tip")
        self.d_prest = Dial("jz.p_rest", 0, 0.5, 0.12, tip_key="jz.p_rest.tip")
        self.d_phold = Dial("jz.p_hold", 0, 0.6, 0.25, tip_key="jz.p_hold.tip")
        self.d_density = Dial("jz.density", 1, 8, 5, decimals=1, tip_key="jz.density.tip")
        self.d_sync = Dial("jz.sync", 0, 1, 0.4, tip_key="jz.sync.tip")
        for d in (self.d_low, self.d_high, self.d_prest, self.d_phold):
            d.released.connect(self._rebuild_problem)
        for d in (self.d_density, self.d_sync):
            d.valueChanged.connect(self._targets_changed)
        mel.add_layout(dial_grid([self.d_low, self.d_high, self.d_density, self.d_prest, self.d_phold, self.d_sync], 3))
        lay.addWidget(mel)

        fit = Card("jz.weights")
        fit.add(tlabel("jz.weights.hint", "Muted", wrap=True))
        self.weight_dials = {}
        for k in CRITERIA:
            d = Dial(f"crit.{k}", 0, 5, DEFAULT_WEIGHTS[k], decimals=1, tip_key=f"crit.{k}.tip")
            d.valueChanged.connect(self._weights_changed)
            self.weight_dials[k] = d
        fit.add_layout(dial_grid(list(self.weight_dials.values()), 3))
        lay.addWidget(fit)

        snd = Card("jz.sound")
        self.lead = QComboBox()
        self.lead.addItems(["Rhodes", "Vibes", "Sax"])
        row = QHBoxLayout()
        row.addWidget(tlabel("jz.lead", "Muted"))
        row.addWidget(self.lead, 1)
        snd.add_layout(row)
        self.vol = {
            "lead": Dial("jz.vol.lead", 0, 1, 0.9, size=46),
            "bass": Dial("jz.vol.bass", 0, 1, 0.8, size=46),
            "comp": Dial("jz.vol.comp", 0, 1, 0.5, size=46),
            "drums": Dial("jz.vol.drums", 0, 1, 0.5, size=46),
        }
        snd.add_layout(dial_grid(list(self.vol.values()), 4))
        self.b_midi = tbutton("btn.export_midi", icon="export")
        self.b_midi.clicked.connect(self._export_midi)
        self.b_wav = tbutton("btn.export_wav", icon="export")
        self.b_wav.clicked.connect(self._export_wav)
        row = QHBoxLayout()
        row.addWidget(self.b_midi)
        row.addWidget(self.b_wav)
        snd.add_layout(row)
        lay.addWidget(snd)
        lay.addStretch(1)
        scroll.setWidget(w)
        return scroll

    # ------------------------------------------------------------- centre
    def _build_center(self):
        split = QSplitter(Qt.Vertical)
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        ro, self.fitness_label = readout("jz.fitness")
        header.addLayout(ro)
        header.addSpacing(20)
        self.show_mode = QComboBox()
        self.show_mode.currentIndexChanged.connect(lambda _: self.update_display())
        header.addWidget(tlabel("jz.show", "Muted"))
        header.addWidget(self.show_mode)
        header.addStretch(1)
        self.b_play = tbutton("btn.play", primary=True, icon="play")
        self.b_play.clicked.connect(self._play)
        self.b_stop = tbutton("btn.stop", icon="stop")
        self.b_stop.clicked.connect(self._stop)
        for b in (self.b_play, self.b_stop):
            header.addWidget(b)
        tl.addLayout(header)

        mid = QHBoxLayout()
        mid.setSpacing(12)
        roll_card = Card()
        self.roll = PianoRoll()
        roll_card.add(self.roll)
        self.legend = FlowLayout()
        self.role_chips = [Chip(lambda i=i: theme.ROLE_COLORS[i], f"role.{i}", outlined=(i == 3)) for i in range(5)]
        self.source_chips = [Chip(lambda s=s: theme.SOURCE_COLORS[s], k) for s, k in
                             ((1, "src.memory"), (2, "src.adjusted"), (0, "src.random"), (3, "src.best"))]
        for chip in self.role_chips + self.source_chips:
            self.legend.addWidget(chip)
        roll_card.add_layout(self.legend)
        mid.addWidget(roll_card, 1)
        bars_card = Card("jz.breakdown")
        bars_card.setFixedWidth(272)
        self.bars = ScoreBars(list(CRITERIA), "crit")
        bars_card.add(self.bars)
        bars_card.add(tlabel("jz.breakdown.hint", "Muted", wrap=True))
        bars_card.outer.addStretch(1)
        mid.addWidget(bars_card)
        tl.addLayout(mid, 1)
        split.addWidget(top)

        self.bottom = QTabWidget()
        self.bottom.setObjectName("Panel")
        self.bottom.tabBar().setDrawBase(False)
        self.conv = ConvergenceView(self.runner)
        self.mem = MemoryAndStep(self.runner, self.adapter)
        self.mem.memory.row_selected.connect(self._row_selected)
        self.bottom.addTab(self.conv, "")
        self.bottom.addTab(self.mem, "")
        split.addWidget(self.bottom)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self._retranslate()
        return split

    def _retranslate(self):
        self.bottom.setTabText(0, tr("tab.convergence"))
        self.bottom.setTabText(1, tr("tab.memory").replace("&", "&&"))
        idx = max(0, self.show_mode.currentIndex())
        self.show_mode.blockSignals(True)
        self.show_mode.clear()
        self.show_mode.addItems([tr("jz.show.best"), tr("jz.show.last"), tr("jz.show.selected")])
        self.show_mode.setCurrentIndex(idx)
        self.show_mode.blockSignals(False)
        self._update_legend()

    def _update_legend(self):
        for chip in self.role_chips:
            chip.setVisible(not self._legend_sources)
        for i, chip in enumerate(self.source_chips):
            chip.setVisible(self._legend_sources and (i < 3 or self.params.variant == "ghs"))
        self.legend.invalidate()

    # ------------------------------------------------------------- problem
    def _progression_changed(self, name):
        self.key.blockSignals(True)
        self.key.setCurrentIndex(theory.PROGRESSIONS[name]["default_key"])
        self.key.blockSignals(False)
        self._rebuild_problem()

    def _rebuild_problem(self):
        low, high = int(self.d_low.value()), int(self.d_high.value())
        if high - low < 7:
            high = low + 7
            self.d_high.setValue(high, emit=False)
        chords = theory.build_progression(self.prog.currentText(), self.key.currentIndex(), int(self.d_choruses.value()))
        self.problem = MelodyProblem(
            chords, low=low, high=high,
            weights={k: d.value() for k, d in self.weight_dials.items()},
            target_density=self.d_density.value(), target_syncopation=self.d_sync.value(),
            p_rest=self.d_prest.value(), p_hold=self.d_phold.value(),
        )
        self.backing = backing_mod.build(chords)
        self.selected_row = None
        prob = self.problem
        self.runner.set_factory(lambda: (prob.variables(), prob, True))

    def _factory_copy(self):
        prob = copy.deepcopy(self.problem)
        return lambda: (prob.variables(), prob, True)

    def _weights_changed(self, _=None):
        self.problem.weights = {k: d.value() for k, d in self.weight_dials.items()}
        self._reevaluate()

    def _targets_changed(self, _=None):
        self.problem.target_density = self.d_density.value()
        self.problem.target_syncopation = self.d_sync.value()
        self._reevaluate()

    def _reevaluate(self):
        if self.runner.engine is not None:
            self.runner.engine.reevaluate()
            self.runner.refreshed.emit()

    def _on_reset(self):
        self.selected_row = None
        self._update_legend()

    def _row_selected(self, r):
        self.selected_row = r
        self.show_mode.setCurrentIndex(2)
        self.update_display()

    def _compare(self):
        CompareDialog(self._factory_copy(), copy.copy(self.params), self.adapter, min(self.params.ni, 5000), self).exec()

    # ------------------------------------------------------------- display
    def _current(self):
        eng = self.runner.engine
        if eng is None:
            return None, None
        mode = self.show_mode.currentIndex()
        if mode == 1 and eng.last is not None:
            return eng.last.harmony, eng.last.source
        if mode == 2 and self.selected_row is not None and self.selected_row < len(eng.memory):
            return eng.memory[self.selected_row], None
        return eng.best, None

    def update_display(self):
        x, sources = self._current()
        if x is None:
            return
        p = self.problem
        notes = p.decode(x)
        if sources is not None:
            colors = [theme.SOURCE_COLORS[int(sources[n.start])] for n in notes]
        else:
            colors = [theme.ROLE_COLORS[p.role(notes[i], notes[i + 1] if i + 1 < len(notes) else None)]
                      for i in range(len(notes))]
        self.roll.set_data(p, notes, colors, sources)
        comps = p.components(x)
        self.bars.set_values(comps, p.weights)
        self.fitness_label.setText(f"{p.score(comps) * 100:.1f}")
        if (sources is not None) != self._legend_sources:
            self._legend_sources = sources is not None
            self._update_legend()

    # ------------------------------------------------------------- audio
    def _render(self):
        x, _ = self._current()
        if x is None:
            return None
        notes = self.problem.to_beats(self.problem.decode(x))
        lead = render.LEAD_INSTRUMENTS[self.lead.currentIndex()]
        audio = render.render(notes, self.backing, theory.total_beats(self.problem.chords), self.d_tempo.value(),
                              self.d_swing.value(), lead=lead, volumes={k: d.value() for k, d in self.vol.items()})
        return notes, audio

    def _play(self):
        out = self._render()
        if out is None:
            return
        if not self.player.play(out[1], render.SR):
            QMessageBox.warning(self, tr("err.audio"), self.player.error or "")
            return
        self.play_timer.start()

    def _stop(self):
        self.player.stop()
        self.play_timer.stop()
        self.roll.set_playhead(None)

    def _update_playhead(self):
        pos = self.player.position
        if pos is None:
            self._stop()
            return
        beats = pos / (60.0 / self.d_tempo.value())
        slot = beats * 2
        if slot > self.problem.n_slots:
            self.roll.set_playhead(None)
        else:
            self.roll.set_playhead(slot)

    def _export_midi(self):
        x, _ = self._current()
        if x is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("btn.export_midi"), "harmony_search_jazz.mid", "MIDI (*.mid)")
        if not path:
            return
        notes = self.problem.to_beats(self.problem.decode(x))
        lead = render.LEAD_INSTRUMENTS[self.lead.currentIndex()]
        midi.export_midi(path, notes, self.backing, self.problem.chords, self.d_tempo.value(), self.d_swing.value(), lead)

    def _export_wav(self):
        out = self._render()
        if out is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("btn.export_wav"), "harmony_search_jazz.wav", "WAV (*.wav)")
        if path:
            save_wav(path, out[1], render.SR)
