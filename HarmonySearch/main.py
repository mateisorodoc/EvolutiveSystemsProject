"""Harmony Search Studio - entry point.

    python main.py              light theme (default, best on projectors)
    python main.py --dark       dark theme
    python main.py --maximized  start maximised
"""

import sys


def main():
    import pyqtgraph as pg
    from PySide6.QtWidgets import QApplication

    from hsapp.ui import theme

    app = QApplication(sys.argv)
    app.setApplicationName("Harmony Search Studio")
    app.setStyle("Fusion")
    theme.apply("dark" if "--dark" in sys.argv else "light")
    app.setFont(theme.font(theme.FS_BODY))
    app.setStyleSheet(theme.stylesheet())
    pg.setConfigOptions(antialias=True, foreground=theme.MUTED)

    from hsapp.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1560, 940)
    win.showMaximized() if "--maximized" in sys.argv else win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
