"""Audio playback, microphone recording and file I/O."""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import numpy as np

try:
    import sounddevice as sd
except Exception:  # PortAudio missing: the app still runs, without sound
    sd = None

try:
    import soundfile as sf
except Exception:
    sf = None


def audio_available() -> bool:
    return sd is not None


class Player:
    """Plays one buffer at a time and reports the playback position."""

    def __init__(self):
        self._start = 0.0
        self._duration = 0.0
        self.error: Optional[str] = None

    def play(self, audio: np.ndarray, sr: int) -> bool:
        self.stop()
        if sd is None:
            self.error = "sounddevice / PortAudio not available"
            return False
        try:
            sd.play(np.asarray(audio, dtype=np.float32), sr)
        except Exception as e:  # no output device, etc.
            self.error = str(e)
            return False
        self._start = time.perf_counter()
        self._duration = len(audio) / sr
        return True

    def stop(self):
        if sd is not None:
            try:
                sd.stop()
            except Exception:
                pass
        self._duration = 0.0

    @property
    def position(self) -> Optional[float]:
        """Seconds since playback started, or None if nothing is playing."""
        if self._duration <= 0:
            return None
        p = time.perf_counter() - self._start
        if p > self._duration:
            self._duration = 0.0
            return None
        return p


class Recorder:
    """Records from the default input device until ``stop`` or ``max_seconds``."""

    def __init__(self, sr: int = 44100, max_seconds: float = 10.0):
        self.sr = sr
        self.max_seconds = max_seconds
        self._chunks = []
        self._stream = None
        self._lock = threading.Lock()
        self.level = 0.0
        self.error: Optional[str] = None

    @property
    def recording(self) -> bool:
        return self._stream is not None

    @property
    def elapsed(self) -> float:
        with self._lock:
            return sum(len(c) for c in self._chunks) / self.sr

    def start(self) -> bool:
        if sd is None:
            self.error = "sounddevice / PortAudio not available"
            return False
        self._chunks = []

        def callback(indata, frames, time_info, status):
            with self._lock:
                self._chunks.append(indata[:, 0].copy())
            self.level = float(np.sqrt(np.mean(indata[:, 0] ** 2)))

        try:
            self._stream = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32", callback=callback)
            self._stream.start()
        except Exception as e:
            self.error = str(e)
            self._stream = None
            return False
        return True

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        with self._lock:
            data = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
        return data[: int(self.max_seconds * self.sr)]


def load_audio(path: str) -> Tuple[np.ndarray, int]:
    if sf is not None:
        data, sr = sf.read(path, always_2d=False)
        return np.asarray(data, dtype=np.float64), int(sr)
    from scipy.io import wavfile

    sr, data = wavfile.read(path)
    data = np.asarray(data, dtype=np.float64)
    if np.issubdtype(np.asarray(data).dtype, np.integer):
        data = data / np.iinfo(data.dtype).max
    return data, int(sr)


def save_wav(path: str, audio: np.ndarray, sr: int):
    audio = np.clip(np.asarray(audio, dtype=np.float32), -1, 1)
    if sf is not None:
        sf.write(path, audio, sr, subtype="PCM_16")
        return
    from scipy.io import wavfile

    wavfile.write(path, sr, (audio * 32767).astype(np.int16))
