"""Harmony Search composes a jazz line. Run with:  python main.py"""

import sys

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDial,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import melody as mel
import sound
from harmony_search import HarmonySearch

ACCENT = "#1f5fa8"        # the only colour: chord tones and the best-fitness curve
GRAY = "#b8bcc4"
TICKS_PER_SECOND = 10     # how often the Run timer fires


class LabeledDial(QWidget):
    """A dial with its name above and its value below.

    A QDial can only hold whole numbers (0, 1, 2, ...), so we give each dial
    a `step`: the real value is  low + position * step.
    Example: HMCR goes from 0 to 1 in steps of 0.01, so position 90 means 0.90.
    The rest of the program only calls value() and never sees the positions.
    """

    def __init__(self, title, low, high, start, step=1, unit="", tip=""):
        super().__init__()
        self.low = low
        self.step = step
        self.unit = unit

        self.dial = QDial()
        self.dial.setRange(0, round((high - low) / step))
        self.dial.setValue(round((start - low) / step))
        self.dial.setNotchesVisible(True)
        self.dial.setFixedSize(64, 64)
        self.setToolTip(tip)

        name = QLabel(title)
        name.setAlignment(Qt.AlignCenter)
        self.value_label = QLabel()
        self.value_label.setAlignment(Qt.AlignCenter)

        column = QVBoxLayout(self)
        column.addWidget(name)
        column.addWidget(self.dial, alignment=Qt.AlignCenter)
        column.addWidget(self.value_label)

        self.valueChanged = self.dial.valueChanged    # so others can connect to it
        self.dial.valueChanged.connect(self.show_value)
        self.show_value()

    def value(self):
        v = self.low + self.dial.value() * self.step
        if self.step >= 1:
            return int(round(v))       # whole-number dials give ints
        return round(v, 2)

    def setValue(self, v):
        self.dial.setValue(round((v - self.low) / self.step))

    def show_value(self):
        if self.step >= 1:
            text = str(self.value())
        else:
            text = f"{self.value():.2f}"    # always two decimals: 0.90, not 0.9
        self.value_label.setText(text + self.unit)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Harmony Search: jazz melody")
        self.last = None   # result of the last improvisation (shown in the explanation)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(self.build_title())
        layout.addLayout(self.build_dials())
        layout.addLayout(self.build_buttons())
        layout.addWidget(self.build_plots(), 3)
        layout.addLayout(self.build_texts(), 2)

        # Qt programs do not loop by themselves. While "Run" is on, this timer calls
        # run_tick() 10 times per second; in between, Qt redraws the window and handles clicks.
        self.timer = QTimer()
        self.timer.setInterval(1000 // TICKS_PER_SECOND)
        self.timer.timeout.connect(self.run_tick)

        self.reset()

    # ================================================================== building the window
    def build_title(self):
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Harmony Search composes a jazz line")
        title.setFont(QFont(self.font().family(), 18, QFont.Bold))
        intro = QLabel("32 eighth notes over Dm7 | G7 | Cmaj7 | Cmaj7. Every note is one variable. "
                       "Turn the dials, press Step to watch one improvisation, or Run to let the band practise.")
        intro.setWordWrap(True)
        column.addWidget(title)
        column.addWidget(intro)
        return box

    def build_dials(self):
        # the algorithm's parameters
        self.hms = LabeledDial("HMS", 2, 50, 10, tip="Harmony Memory Size: how many melodies are remembered. "
                                                     "Changing it restarts the search.")
        self.hmcr = LabeledDial("HMCR", 0, 1, 0.9, step=0.01,
                                tip="Probability that a note is taken from memory (otherwise it is random).")
        self.par = LabeledDial("PAR", 0, 1, 0.3, step=0.01,
                               tip="Probability that a note taken from memory is moved a little.")
        self.bw = LabeledDial("bw", 1, 6, 2, unit=" semitones", tip="Bandwidth: the biggest move of a pitch adjustment.")
        self.ni = LabeledDial("NI", 100, 5000, 2000, step=100, tip="Number of Improvisations: when the search stops.")
        self.speed = LabeledDial("Speed", 10, 500, 50, step=10, unit=" / s", tip="Improvisations per second while running.")
        algorithm = QGroupBox("Harmony Search parameters")
        row = QHBoxLayout(algorithm)
        for dial in (self.hms, self.hmcr, self.par, self.bw, self.ni, self.speed):
            row.addWidget(dial)

        # the fitness function's weights
        tips = {"Chord tones": "Notes on the beat should belong to the chord.",
                "Smoothness": "Prefer small steps to big leaps.",
                "Ending on C": "The last note should be C, the home note."}
        starts = {"Chord tones": 6, "Smoothness": 4, "Ending on C": 2}
        self.weight_dials = {}
        goals = QGroupBox("What makes a good melody? (weights)")
        row2 = QHBoxLayout(goals)
        for name in mel.CRITERIA:
            dial = LabeledDial(name, 0, 10, starts[name], tip=tips[name])
            dial.valueChanged.connect(self.weights_changed)
            self.weight_dials[name] = dial
            row2.addWidget(dial)

        # what each dial does when it is turned
        self.hms.valueChanged.connect(self.reset)
        for dial in (self.hmcr, self.par, self.bw):
            dial.valueChanged.connect(self.parameters_changed)

        dials = QHBoxLayout()
        dials.addWidget(algorithm, 2)
        dials.addWidget(goals, 1)
        return dials

    def build_buttons(self):
        reset_button = QPushButton("Reset")
        step_button = QPushButton("Step")
        self.run_button = QPushButton("Run")
        self.run_button.setDefault(True)
        play_button = QPushButton("Play best melody")
        self.status = QLabel()

        reset_button.clicked.connect(self.reset)
        step_button.clicked.connect(self.step_once)
        self.run_button.clicked.connect(self.toggle_run)
        play_button.clicked.connect(self.play)

        row = QHBoxLayout()
        for button in (reset_button, step_button, self.run_button, play_button):
            row.addWidget(button)
        row.addSpacing(20)
        row.addWidget(self.status, 1)
        return row

    def build_plots(self):
        figure = Figure(figsize=(10, 3.2), tight_layout=True)
        self.roll_axes = figure.add_subplot(1, 3, (1, 2))   # takes 2 of 3 columns
        self.curve_axes = figure.add_subplot(1, 3, 3)
        self.canvas = FigureCanvasQTAgg(figure)
        return self.canvas

    def build_texts(self):
        self.memory_text = QPlainTextEdit(readOnly=True)
        self.explain_text = QPlainTextEdit(readOnly=True)
        mono = QFont("Consolas" if sys.platform == "win32" else "Menlo", 10)
        row = QHBoxLayout()
        for heading, text_box in (("Harmony memory", self.memory_text),
                                  ("Last improvisation, explained", self.explain_text)):
            text_box.setFont(mono)
            text_box.setLineWrapMode(QPlainTextEdit.NoWrap)
            column = QVBoxLayout()
            column.addWidget(QLabel(f"<b>{heading}</b>"))
            column.addWidget(text_box)
            row.addLayout(column)
        return row

    # ================================================================== the search
    def current_weights(self):
        return {name: dial.value() for name, dial in self.weight_dials.items()}

    def score(self, melody):
        """The fitness function given to Harmony Search."""
        return mel.fitness(melody, self.current_weights())

    def reset(self):
        self.hs = HarmonySearch(
            n_vars=mel.N_NOTES, low=mel.LOWEST, high=mel.HIGHEST, fitness=self.score,
            hms=self.hms.value(), hmcr=self.hmcr.value(), par=self.par.value(), bw=self.bw.value(),
        )
        self.last = None
        self.refresh()

    def parameters_changed(self):
        # HMCR, PAR and bw can change while the search is running
        self.hs.hmcr = self.hmcr.value()
        self.hs.par = self.par.value()
        self.hs.bw = self.bw.value()
        self.refresh()

    def weights_changed(self):
        # a new fitness function: every melody in memory gets a new score
        self.hs.rescore()
        self.refresh()

    def finished(self):
        return self.hs.iteration >= self.ni.value()

    def step_once(self):
        if not self.finished():
            self.last = self.hs.step()
        self.refresh()

    def toggle_run(self):
        if self.timer.isActive():
            self.timer.stop()
            self.run_button.setText("Run")
        else:
            self.timer.start()
            self.run_button.setText("Pause")

    def run_tick(self):
        steps_per_tick = self.speed.value() // TICKS_PER_SECOND
        for _ in range(steps_per_tick):
            if self.finished():
                self.toggle_run()
                break
            self.last = self.hs.step()
        self.refresh()

    def play(self):
        best, _ = self.hs.best()
        error = sound.play(best)
        if error:
            QMessageBox.warning(self, "No sound", error)

    # ================================================================== showing the results
    def refresh(self):
        best, best_score = self.hs.best()
        self.status.setText(f"Improvisation {self.hs.iteration} of {self.ni.value()}"
                            f"     Best fitness: {best_score * 100:.1f} / 100")
        self.draw_melody(best, best_score)
        self.draw_curve()
        self.canvas.draw_idle()
        self.memory_text.setPlainText(self.memory_report())
        self.explain_text.setPlainText(self.explanation())

    def draw_melody(self, best, best_score):
        ax = self.roll_axes
        ax.clear()
        for i, midi in enumerate(best):
            if mel.is_chord_tone(best, i):
                color = ACCENT
            else:
                color = GRAY
            ax.barh(midi, 0.9, left=i, height=0.8, color=color)     # one bar per note
        for bar, chord in enumerate(mel.CHORDS):
            x = bar * mel.NOTES_PER_BAR
            ax.axvline(x, color="#dddddd", linewidth=1)
            ax.text(x + 0.2, mel.HIGHEST + 1.3, chord.name, fontweight="bold")
        ticks = [m for m in range(mel.LOWEST, mel.HIGHEST + 1) if m % 12 in (0, 4, 7)]   # C, E and G
        ax.set_yticks(ticks, [mel.note_name(m) for m in ticks])
        ax.set_xticks(range(0, mel.N_NOTES + 1, 8), ["bar 1", "bar 2", "bar 3", "bar 4", "end"])
        ax.set_xlim(0, mel.N_NOTES)
        ax.set_ylim(mel.LOWEST - 1, mel.HIGHEST + 3)
        ax.set_title(f"Best melody (blue = chord tone)   fitness {best_score * 100:.1f}", loc="left", fontsize=10)

    def draw_curve(self):
        ax = self.curve_axes
        ax.clear()
        ax.plot([s * 100 for s in self.hs.history], color=ACCENT)
        ax.set_xlabel("improvisation")
        ax.set_ylim(0, 100)
        ax.set_title("Best fitness in memory", loc="left", fontsize=10)
        ax.grid(alpha=0.3)

    def memory_report(self):
        best = self.hs.scores.index(max(self.hs.scores))
        worst = self.hs.worst_index()
        lines = [" #  fitness        melody"]
        for i in range(self.hs.hms):
            if i == best:
                label = "best"
            elif i == worst:
                label = "worst"
            else:
                label = ""
            score = self.hs.scores[i] * 100
            notes = " ".join(f"{mel.note_name(m):<3}" for m in self.hs.memory[i])
            lines.append(f"{i + 1:>2}  {score:5.1f}  {label:<5}   {notes}")
        return "\n".join(lines)

    def explanation(self):
        if self.last is None:
            return "Press Step to improvise one new melody and see every decision here."
        last = self.last
        hmcr = last["hmcr"]
        par = last["par"]
        worst = last["worst_score"] * 100

        if last["replaced"] is None:
            verdict = f"It is not better than the worst melody in memory ({worst:.1f}), so it is thrown away."
        else:
            verdict = (f"It is better than the worst melody in memory ({worst:.1f}), "
                       f"so it replaces harmony #{last['replaced'] + 1}.")

        lines = [
            f"Improvisation {self.hs.iteration}: the new melody scores {last['score'] * 100:.1f}.",
            verdict,
            "",
            f"P(memory)   = HMCR x (1 - PAR) = {hmcr * (1 - par):.2f}",
            f"P(adjusted) = HMCR x PAR       = {hmcr * par:.2f}",
            f"P(random)   = 1 - HMCR         = {1 - hmcr:.2f}",
            "",
            "note  decision  r1 vs HMCR    from  r2 vs PAR     result",
        ]
        for i, step in enumerate(last["log"]):
            lines.append(explain_note(i, step, hmcr, par))
        return "\n".join(lines)


def compare(r, limit):
    """Show a random number next to its limit, e.g. '0.42 < 0.90' or '0.95 >= 0.90'."""
    if r < limit:
        return f"{r:.2f} < {limit:.2f}"
    return f"{r:.2f} >= {limit:.2f}"


def explain_note(i, step, hmcr, par):
    """One line of the explanation table, for note number i."""
    if step["how"] == "random":
        source = "-"
        r2_text = "-"
        result = mel.note_name(step["value"])
    else:
        source = f"#{step['row'] + 1}"
        r2_text = compare(step["r2"], par)
        if step["how"] == "adjusted":
            result = f"{mel.note_name(step['before'])} -> {mel.note_name(step['value'])}"
        else:
            result = mel.note_name(step["value"])
    r1_text = compare(step["r1"], hmcr)
    return f"{i + 1:>4}  {step['how']:<8}  {r1_text:<12}  {source:<4}  {r2_text:<12}  {result}"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)   # light, like the matplotlib plots
    window = MainWindow()
    window.resize(1200, 900)
    window.show()
    sys.exit(app.exec())
