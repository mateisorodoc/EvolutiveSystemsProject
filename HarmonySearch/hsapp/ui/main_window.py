"""Main window: header with language and theme toggles + the three tabs."""

from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from ..audio.io import Player
from . import theme
from .i18n import I18N, bind, tr
from .jazz_tab import JazzTab
from .learn_tab import LearnTab
from .synth_tab import SynthTab
from .widgets import Segmented, tlabel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        bind(self.setWindowTitle, "app.title")
        self.player = Player()

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(20, 14, 20, 16)
        lay.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(tlabel("app.title", "Title"))
        titles.addWidget(tlabel("app.subtitle", "Subtitle"))
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(Segmented([("light", "theme.light"), ("dark", "theme.dark")], theme.NAME, self.set_theme))
        header.addSpacing(8)
        self.lang = Segmented([("en", "lang.en"), ("ro", "lang.ro")], I18N.lang, I18N.set_lang)
        header.addWidget(self.lang)
        lay.addLayout(header)
        lay.addSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("Main")
        self.tabs.tabBar().setDrawBase(False)
        self.jazz = JazzTab(self.player)
        self.synth = SynthTab(self.player)
        self.learn = LearnTab()
        self.tabs.addTab(self.jazz, "")
        self.tabs.addTab(self.synth, "")
        self.tabs.addTab(self.learn, "")
        self.tabs.currentChanged.connect(self._tab_changed)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        I18N.changed.connect(self._retranslate)
        self._retranslate()

    def set_theme(self, name: str):
        theme.apply(name)
        QApplication.instance().setStyleSheet(theme.stylesheet())
        theme.THEME.changed.emit()

    def _retranslate(self):
        for i, key in enumerate(("tab.jazz", "tab.synth", "tab.learn")):
            self.tabs.setTabText(i, tr(key))

    def _tab_changed(self, _):
        # only one search runs at a time, so the visible one gets the whole CPU
        for tab in (self.jazz, self.synth):
            if tab is not self.tabs.currentWidget():
                tab.runner.pause()
        self.player.stop()

    def closeEvent(self, e):
        self.jazz.runner.pause()
        self.synth.runner.pause()
        self.player.stop()
        if self.synth.recorder.recording:
            self.synth.recorder.stop()
        super().closeEvent(e)
