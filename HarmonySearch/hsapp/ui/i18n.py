"""English / Romanian translations with live switching."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .strings import STRINGS


class _I18n(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.lang = "en"

    def set_lang(self, lang: str):
        if lang != self.lang:
            self.lang = lang
            self.changed.emit()


I18N = _I18n()


def tr(key: str, **kw) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    s = entry[1] if I18N.lang == "ro" else entry[0]
    return s.format(**kw) if kw else s


def bind(setter, key: str, **kw):
    """Call ``setter(tr(key))`` now and again whenever the language changes."""

    def apply():
        try:
            setter(tr(key, **kw))
        except RuntimeError:  # the widget was deleted
            try:
                I18N.changed.disconnect(apply)
            except Exception:
                pass

    apply()
    I18N.changed.connect(apply)
    return apply
