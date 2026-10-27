"""Tab 2: match a recorded / loaded / random sound with a subtractive synth tuned by Harmony Search."""

from __future__ import annotations

import copy
import json
from typing import Dict, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..audio import dsp, matcher, synth
from ..audio.dsp import SR
from ..audio.io import Player, Recorder, load_audio, save_wav
from ..hs import HSParams
from . import theme
from .hs_panel import CompareDialog, ConvergenceView, HSPanel, HSRunner, MemoryAndStep, ProblemAdapter
from .i18n import I18N, bind, tr
from .widgets import LEFT_W, RIGHT_W, Card, Dial, ScoreBars, dial_grid, dial_group, readout, tbutton, tlabel

SHOW_BEST, SHOW_LAST, SHOW_SELECTED, SHOW_MANUAL = range(4)


class SynthAdapter(ProblemAdapter):
    maximize = False
    col_width = 74

    def __init__(self, tab: "SynthTab"):
        self.tab = tab

    def names(self):
        return [tr(f"syn.{k}") for k in self.tab.problem.free_keys]

    def cell_text(self, j, v):
        prm = synth.PARAM_BY_KEY[self.tab.problem.free_keys[j]]
        return prm.format(prm.to_value(v))

    def cell_color(self, j, v):
        return theme.lerp_color("#1c2540", "#3d4f8f", float(v))

    def fitness_text(self, f):
        return f"{f:.4f}"


class SynthTab(QWidget):
    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self.player = player
        self.recorder = Recorder(sr=44100, max_seconds=matcher.MAX_SECONDS)
        self.params = HSParams(variant="classic", hms=20, hmcr=0.9, par=0.35, bw=0.05, par_min=0.1, par_max=0.7,
                               bw_min=0.005, bw_max=0.2, ni=3000)
        self.runner = HSRunner(self.params, self)
        self.adapter = SynthAdapter(self)
        self.raw_target: Optional[np.ndarray] = None
        self.target: Optional[matcher.TargetFeatures] = None
        self.true_knobs: Optional[Dict[str, float]] = None
        self.problem: Optional[matcher.MatchProblem] = None
        self.knobs: Dict[str, float] = synth.default_knobs()
        self.selected_row: Optional[int] = None
        self._shown_key = None
        self.rng = np.random.default_rng()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(16)
        root.addWidget(self._build_left())
        root.addWidget(self._build_center(), 1)
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFixedWidth(RIGHT_W)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hs_panel = HSPanel(self.runner, ni_max=50000)
        self.hs_panel.compare_requested.connect(self._compare)
        right.setWidget(self.hs_panel)
        root.addWidget(right)

        self.runner.refreshed.connect(self.update_display)
        self.runner.running_changed.connect(self._running_changed)
        self.runner.reset_done.connect(lambda: setattr(self, "selected_row", None))
        I18N.changed.connect(self._retranslate)
        self.rec_timer = QTimer(self)
        self.rec_timer.setInterval(50)
        self.rec_timer.timeout.connect(self._rec_tick)
        self._random_target()

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

        tgt = Card("sy.target")
        row = QHBoxLayout()
        self.b_load = tbutton("sy.load", icon="open")
        self.b_load.clicked.connect(self._load)
        self.b_rec = tbutton("sy.record", checkable=True, tip_key="sy.record.tip", icon="record")
        self.b_rec.clicked.connect(self._toggle_record)
        row.addWidget(self.b_load)
        row.addWidget(self.b_rec)
        tgt.add_layout(row)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setVisible(False)
        tgt.add(self.level)
        row = QHBoxLayout()
        self.b_random = tbutton("sy.random", tip_key="sy.random.tip", icon="shuffle")
        self.b_random.clicked.connect(self._random_target)
        self.d_rand_len = Dial("sy.rand_len", 0.5, 4.0, 1.5, decimals=1, unit="s", size=44)
        row.addWidget(self.b_random, 1)
        row.addWidget(self.d_rand_len)
        tgt.add_layout(row)
        self.b_play_target = tbutton("sy.play_target", icon="play")
        self.b_play_target.clicked.connect(self._play_target)
        self.b_play = tbutton("sy.play_synth", primary=True, icon="play")
        self.b_play.clicked.connect(self._play_synth)
        self.b_ab = tbutton("sy.ab", tip_key="sy.ab.tip", icon="listen")
        self.b_ab.clicked.connect(self._play_ab)
        row = QHBoxLayout()
        row.addWidget(self.b_play_target)
        row.addWidget(self.b_play)
        row.addWidget(self.b_ab)
        tgt.add_layout(row)
        self.b_wav = tbutton("btn.export_wav", icon="export")
        self.b_wav.clicked.connect(self._export_wav)
        self.b_patch = tbutton("sy.save_patch", icon="save")
        self.b_patch.clicked.connect(self._save_patch)
        row = QHBoxLayout()
        row.addWidget(self.b_wav)
        row.addWidget(self.b_patch)
        tgt.add_layout(row)
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        tgt.add(self.info)
        lay.addWidget(tgt)

        pc = Card("sy.pitch")
        self.lock = QCheckBox()
        bind(self.lock.setText, "sy.lock")
        bind(self.lock.setToolTip, "sy.lock.tip")
        self.lock.setChecked(True)
        self.lock.toggled.connect(lambda _: self._rebuild_problem())
        pc.add(self.lock)
        pc.add(tlabel("sy.lock.hint", "Muted", wrap=True))
        lay.addWidget(pc)

        fit = Card("sy.weights")
        fit.add(tlabel("sy.weights.hint", "Muted", wrap=True))
        self.weight_dials = {}
        for k in matcher.COST_KEYS:
            d = Dial(f"cost.{k}", 0, 5, matcher.DEFAULT_COST_WEIGHTS[k], decimals=1, tip_key=f"cost.{k}.tip",
                     size=46)
            d.valueChanged.connect(self._weights_changed)
            self.weight_dials[k] = d
        self.d_maxlen = Dial("sy.maxlen", 0.5, 10.0, 10.0, decimals=1, unit="s", tip_key="sy.maxlen.tip",
                            size=46)
        self.d_maxlen.released.connect(self._rebuild_problem)
        fit.add_layout(dial_grid(list(self.weight_dials.values()) + [self.d_maxlen], 4))
        lay.addWidget(fit)

        self.truth_card = Card("sy.truth")
        self.truth_card.add(tlabel("sy.truth.hint", "Muted", wrap=True))
        self.truth = QTableWidget(0, 3)
        self.truth.verticalHeader().setVisible(False)
        self.truth.verticalHeader().setDefaultSectionSize(20)
        self.truth.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.truth.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.truth.setMinimumHeight(360)
        self.truth_card.add(self.truth)
        lay.addWidget(self.truth_card)
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
        ro, self.cost_label = readout("sy.cost")
        header.addLayout(ro)
        header.addSpacing(20)
        self.bars = ScoreBars(list(matcher.COST_KEYS), "cost", invert=True)
        self.bars.setFixedWidth(250)
        header.addWidget(self.bars)
        header.addStretch(1)
        header.addWidget(tlabel("jz.show", "Muted"))
        self.show_mode = QComboBox()
        self.show_mode.currentIndexChanged.connect(lambda _: self.update_display(force=True))
        header.addWidget(self.show_mode)
        header.addStretch(1)
        tl.addLayout(header)

        knobs = Card("sy.synth")
        self.dials: Dict[str, Dial] = {}
        for prm in synth.PARAMS:
            d = Dial(f"syn.{prm.key}", value=prm.default, mapping=(prm.to_value, prm.to_knob), fmt=prm.format,
                     tip_key=f"syn.{prm.key}.tip", size=46)
            d.valueChanged.connect(lambda _v, k=prm.key: self._dial_moved(k))
            self.dials[prm.key] = d
        d = self.dials
        top_row = QHBoxLayout()
        top_row.setSpacing(28)
        top_row.addLayout(dial_group("sy.grp.osc", [d[k] for k in ("pitch", "wave1", "wave2", "detune", "mix", "noise")]))
        top_row.addLayout(dial_group("sy.grp.vib", [d["vib_depth"], d["vib_rate"]]))
        top_row.addStretch(1)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(28)
        bottom_row.addLayout(dial_group("sy.grp.filter", [d[k] for k in ("cutoff", "resonance", "env_amt", "f_decay")]))
        bottom_row.addLayout(dial_group("sy.grp.amp", [d[k] for k in ("attack", "decay", "sustain", "release", "gate")]))
        bottom_row.addStretch(1)
        knobs.add_layout(top_row)
        knobs.add_layout(bottom_row)
        knobs.add(tlabel("sy.synth.hint", "Muted", wrap=True))
        tl.addWidget(knobs)

        self.gfx = pg.GraphicsLayoutWidget()
        cmap = pg.colormap.get("magma")
        self.p_tspec = self.gfx.addPlot(row=0, col=0)
        self.p_sspec = self.gfx.addPlot(row=0, col=1)
        self.img_t = pg.ImageItem()
        self.img_s = pg.ImageItem()
        for plot, img in ((self.p_tspec, self.img_t), (self.p_sspec, self.img_s)):
            plot.addItem(img)
            img.setColorMap(cmap)
            plot.hideAxis("left")
            plot.hideAxis("bottom")
            plot.setMouseEnabled(False, False)
            plot.hideButtons()
        self.p_sspec.setXLink(self.p_tspec)
        self.p_env = self.gfx.addPlot(row=1, col=0)
        self.p_spec = self.gfx.addPlot(row=1, col=1)
        self.p_spec.setLogMode(x=True, y=False)
        ticks = [100, 200, 500, 1000, 2000, 5000, 10000]
        self.p_spec.getAxis("bottom").setTicks([[(np.log10(f), f"{f // 1000}k" if f >= 1000 else str(f)) for f in ticks]])
        self.c_env_t = self.p_env.plot()
        self.c_env_s = self.p_env.plot()
        self.c_spec_t = self.p_spec.plot()
        self.c_spec_s = self.p_spec.plot()
        plots = Card()
        plots.outer.setContentsMargins(8, 8, 8, 8)
        self.gfx.setMinimumHeight(230)
        plots.add(self.gfx)
        tl.addWidget(plots, 1)
        # on short screens (13" laptops) the work area scrolls instead of squeezing the plots
        top_scroll = QScrollArea()
        top_scroll.setWidgetResizable(True)
        top_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        top_scroll.setWidget(top)
        top_scroll.setMinimumHeight(280)
        split.addWidget(top_scroll)

        self.bottom = QTabWidget()
        self.bottom.setObjectName("Panel")
        self.bottom.tabBar().setDrawBase(False)
        self.conv = ConvergenceView(self.runner)
        self.mem = MemoryAndStep(self.runner, self.adapter)
        self.mem.memory.row_selected.connect(self._row_selected)
        self.bottom.addTab(self.conv, "")
        self.bottom.addTab(self.mem, "")
        split.addWidget(self.bottom)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 2)
        split.setSizes([820, 170])
        theme.THEME.changed.connect(self.restyle)
        self.restyle()
        return split

    def restyle(self):
        """Target in a broad muted line, the synth in thin ink on top: the gap between them is the error."""
        self.gfx.setBackground(theme.CARD)
        self.c_env_t.setPen(pg.mkPen(theme.qc(theme.MUTED, 150), width=4))
        self.c_spec_t.setPen(pg.mkPen(theme.qc(theme.MUTED, 150), width=4))
        self.c_env_s.setPen(pg.mkPen(theme.INK, width=1.6))
        self.c_spec_s.setPen(pg.mkPen(theme.INK, width=1.6))
        for plot in (self.p_env, self.p_spec, self.p_tspec, self.p_sspec):
            theme.style_plot(plot, legend=False)
        for plot in (self.p_tspec, self.p_sspec):
            plot.showGrid(x=False, y=False)
        self._retranslate()

    def _retranslate(self):
        self.bottom.setTabText(0, tr("tab.convergence"))
        self.bottom.setTabText(1, tr("tab.memory").replace("&", "&&"))
        idx = max(0, self.show_mode.currentIndex())
        self.show_mode.blockSignals(True)
        self.show_mode.clear()
        self.show_mode.addItems([tr("jz.show.best"), tr("jz.show.last"), tr("jz.show.selected"), tr("sy.show.manual")])
        self.show_mode.setCurrentIndex(idx)
        self.show_mode.blockSignals(False)
        title = dict(color=theme.TEXT, size=f"{theme.FS_CAPTION}px", bold=True)
        self.p_tspec.setTitle(tr("sy.target_spec"), **title)
        self.p_sspec.setTitle(tr("sy.synth_spec"), **title)
        legend = (f"&nbsp;&nbsp;&nbsp;<span style='color:{theme.MUTED}'>{tr('sy.legend.target')}</span>"
                  f"&nbsp;&nbsp;<span style='color:{theme.TEXT}'>{tr('sy.legend.synth')}</span>")
        self.p_env.setTitle(tr("sy.envelope") + legend, **title)
        self.p_spec.setTitle(tr("sy.spectrum") + legend, **title)
        self.p_env.setLabel("bottom", "s")
        self.p_spec.setLabel("bottom", "Hz")
        self._update_info()
        self._update_truth()
        if self.runner.engine is not None:
            self.mem.memory.refresh()

    # ------------------------------------------------------------- target
    def _random_target(self):
        knobs = synth.random_knobs(self.rng)
        n = int(self.d_rand_len.value() * SR)
        audio = synth.render_audio(knobs, n)
        self.set_target(audio, true_knobs=knobs)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("sy.load"), "", tr("sy.audio_files") + " (*.wav *.flac *.ogg *.mp3 *.aiff *.aif)")
        if not path:
            return
        try:
            data, sr = load_audio(path)
        except Exception as e:
            QMessageBox.warning(self, tr("err.load"), str(e))
            return
        self.set_target(matcher.prepare_target(data, sr))

    def _toggle_record(self, on):
        if on:
            self.player.stop()
            if not self.recorder.start():
                self.b_rec.setChecked(False)
                QMessageBox.warning(self, tr("err.mic"), (self.recorder.error or "") + "\n\n" + tr("err.mic.hint"))
                return
            self.level.setVisible(True)
            self.rec_timer.start()
            self.b_rec.setText(tr("sy.stop_record"))
        else:
            self._finish_record()

    def _rec_tick(self):
        self.level.setValue(int(min(1.0, self.recorder.level * 4) * 100))
        el = self.recorder.elapsed
        self.b_rec.setText(f"{tr('sy.stop_record')}  {el:.1f}s")
        if el >= matcher.MAX_SECONDS:
            self.b_rec.setChecked(False)
            self._finish_record()

    def _finish_record(self):
        self.rec_timer.stop()
        self.level.setVisible(False)
        self.b_rec.setText(tr("sy.record"))
        data = self.recorder.stop()
        if len(data) < 0.1 * self.recorder.sr or np.max(np.abs(data)) < 1e-4:
            QMessageBox.information(self, tr("err.mic"), tr("err.silent"))
            return
        self.set_target(matcher.prepare_target(data, self.recorder.sr))

    def set_target(self, audio: np.ndarray, true_knobs: Optional[Dict[str, float]] = None):
        self.raw_target = audio
        self.true_knobs = true_knobs
        self._rebuild_problem(detect_pitch=True)
        self.truth_card.setVisible(true_knobs is not None)

    def _rebuild_problem(self, detect_pitch: bool = False):
        if self.raw_target is None:
            return
        audio = self.raw_target[: int(self.d_maxlen.value() * SR)]
        self.target = matcher.analyse(audio)
        pitch_prm = synth.PARAM_BY_KEY["pitch"]
        if detect_pitch:
            if self.true_knobs is not None:
                # known patch: lock to its true pitch, start the manual view from the default patch
                self.knobs = synth.default_knobs()
                self.knobs["pitch"] = self.true_knobs["pitch"]
            elif self.target.pitch_hz:
                self.knobs["pitch"] = pitch_prm.to_knob(dsp.hz_to_midi(self.target.pitch_hz))
        self.problem = matcher.MatchProblem(
            self.target, lock_pitch=self.lock.isChecked(), locked_pitch_knob=self.knobs["pitch"],
            weights={k: d.value() for k, d in self.weight_dials.items()},
        )
        self.dials["pitch"].setKnob(self.knobs["pitch"], emit=False)
        mel = self.target.mel
        self.img_t.setImage(mel, levels=(-dsp.DB_FLOOR, 0))
        self.img_t.setRect(0, 0, mel.shape[0] * dsp.HOP / SR, dsp.N_MELS)
        self.p_tspec.setXRange(0, self.target.duration, padding=0)
        self._update_info()
        self._update_truth()
        prob = self.problem
        self.runner.set_factory(lambda: (prob.variables(), prob, False))
        self.update_display(force=True)

    def _factory_copy(self):
        prob = copy.deepcopy(self.problem)
        return lambda: (prob.variables(), prob, False)

    def _update_info(self):
        t = self.target
        if t is None:
            return
        if t.pitch_hz:
            pitch = tr("sy.info.pitch", note=dsp.midi_name(dsp.hz_to_midi(t.pitch_hz)), hz=t.pitch_hz, conf=t.pitch_conf * 100)
        else:
            pitch = tr("sy.info.nopitch")
        src = tr("sy.info.known") if self.true_knobs is not None else tr("sy.info.external")
        self.info.setText(tr("sy.info", dur=t.duration, src=src) + "\n" + pitch)

    def _update_truth(self):
        if self.true_knobs is None:
            return
        eng = self.runner.engine
        found = self.problem.knobs(eng.best) if (eng is not None and self.problem is not None) else None
        self.truth.setHorizontalHeaderLabels([tr("sy.truth.param"), tr("sy.truth.true"), tr("sy.truth.found")])
        self.truth.setRowCount(len(synth.PARAMS))
        for i, prm in enumerate(synth.PARAMS):
            tv = self.true_knobs[prm.key]
            cells = [tr(f"syn.{prm.key}"), prm.format(prm.to_value(tv)),
                     prm.format(prm.to_value(found[prm.key])) if found else "—"]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignCenter)
                if c == 2 and found:
                    err = abs(found[prm.key] - tv)
                    it.setBackground(theme.tint(theme.SUCCESS if err < 0.05 else theme.WARNING if err < 0.2 else theme.ERROR,
                                                0.25))
                self.truth.setItem(i, c, it)

    # ------------------------------------------------------------- problem changes
    def _weights_changed(self, _=None):
        if self.problem is None:
            return
        self.problem.weights = {k: d.value() for k, d in self.weight_dials.items()}
        if self.runner.engine is not None:
            self.runner.engine.reevaluate()
            self.runner.refreshed.emit()
        self.update_display(force=True)

    def _dial_moved(self, key):
        if self.runner.running:
            return
        self.knobs[key] = self.dials[key].knob()
        if key == "pitch" and self.problem is not None and self.problem.lock_pitch:
            self.problem.locked_pitch_knob = self.knobs["pitch"]
            if self.runner.engine is not None:
                self.runner.engine.reevaluate()
                self.runner.refreshed.emit()
        if self.show_mode.currentIndex() != SHOW_MANUAL:
            self.show_mode.setCurrentIndex(SHOW_MANUAL)
        else:
            self.update_display(force=True)

    def _running_changed(self, running):
        for k, d in self.dials.items():
            d.setInteractive(not running)
        self.b_random.setEnabled(not running)
        self.b_load.setEnabled(not running)
        self.b_rec.setEnabled(not running)
        self.lock.setEnabled(not running)
        if running and self.show_mode.currentIndex() == SHOW_MANUAL:
            self.show_mode.setCurrentIndex(SHOW_BEST)
        if not running:
            self._update_truth()

    def _row_selected(self, r):
        self.selected_row = r
        if self.show_mode.currentIndex() != SHOW_SELECTED:
            self.show_mode.setCurrentIndex(SHOW_SELECTED)
        else:
            self.update_display(force=True)

    def _compare(self):
        CompareDialog(self._factory_copy(), copy.copy(self.params), self.adapter, min(self.params.ni, 1500), self).exec()

    # ------------------------------------------------------------- display
    def current_knobs(self) -> Dict[str, float]:
        eng = self.runner.engine
        mode = self.show_mode.currentIndex()
        if self.problem is None or eng is None or mode == SHOW_MANUAL:
            k = dict(self.knobs)
            if self.problem is not None and self.problem.lock_pitch:
                k["pitch"] = self.problem.locked_pitch_knob
            return k
        if mode == SHOW_LAST and eng.last is not None:
            return self.problem.knobs(eng.last.harmony)
        if mode == SHOW_SELECTED and self.selected_row is not None and self.selected_row < len(eng.memory):
            return self.problem.knobs(eng.memory[self.selected_row])
        return self.problem.knobs(eng.best)

    def update_display(self, force: bool = False):
        if self.problem is None:
            return
        knobs = self.current_knobs()
        key = tuple(round(knobs[k], 6) for k in synth.KEYS)
        if key == self._shown_key and not force:
            return
        self._shown_key = key
        if self.show_mode.currentIndex() != SHOW_MANUAL:
            for k, d in self.dials.items():
                d.setKnob(knobs[k], emit=False)
        comps = self.problem.components(knobs)
        self.bars.set_values(comps, self.problem.weights)
        self.cost_label.setText(f"{self.problem.cost_of_knobs(knobs):.4f}")
        mel, env, spectrum = self.problem.features_of(knobs)
        self.img_s.setImage(mel, levels=(-dsp.DB_FLOOR, 0))
        self.img_s.setRect(0, 0, mel.shape[0] * dsp.HOP / SR, dsp.N_MELS)
        tt = np.arange(len(self.target.env)) * dsp.HOP / SR
        self.c_env_t.setData(tt, self.target.env)
        self.c_env_s.setData(tt, env)
        self.c_spec_t.setData(dsp.MEL_CENTERS_HZ, self.target.spectrum)
        self.c_spec_s.setData(dsp.MEL_CENTERS_HZ, spectrum)
        if self.true_knobs is not None and not self.runner.running:
            self._update_truth()

    # ------------------------------------------------------------- audio
    def _synth_audio(self):
        return synth.render_audio(self.current_knobs(), self.target.n)

    def _play(self, audio):
        if not self.player.play(audio, SR):
            QMessageBox.warning(self, tr("err.audio"), self.player.error or "")

    def _play_target(self):
        if self.target is not None:
            self._play(self.target.audio)

    def _play_synth(self):
        if self.target is not None:
            self._play(self._synth_audio())

    def _play_ab(self):
        if self.target is not None:
            gap = np.zeros(int(0.4 * SR))
            self._play(np.concatenate([self.target.audio, gap, self._synth_audio()]))

    def _export_wav(self):
        if self.target is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("btn.export_wav"), "harmony_search_synth.wav", "WAV (*.wav)")
        if path:
            save_wav(path, self._synth_audio(), SR)

    def _save_patch(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("sy.save_patch"), "harmony_search_patch.json", "JSON (*.json)")
        if not path:
            return
        knobs = self.current_knobs()
        data = {
            "values": synth.knobs_to_values(knobs),
            "knobs": knobs,
            "cost": self.problem.cost_of_knobs(knobs) if self.problem else None,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
