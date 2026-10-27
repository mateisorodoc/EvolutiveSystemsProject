"""Render a melody + rhythm section to audio with small built-in instruments (no soundfonts)."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Tuple

import numpy as np
from scipy.signal import butter, lfilter

from .backing import BASS, COMP, HAT, RIDE, Event

SR = 44100
LEAD_INSTRUMENTS = ("rhodes", "vibes", "sax")


def swing_time(beat: float, swing: float) -> float:
    """Map straight time (in beats) to swung time. swing = position of the off-beat eighth (0.5 = straight)."""
    b = np.floor(beat)
    f = beat - b
    if f <= 0.5:
        return float(b + f * 2 * swing)
    return float(b + swing + (f - 0.5) * 2 * (1 - swing))


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def _release(n_sound, n_rel):
    env = np.ones(n_sound + n_rel)
    if n_rel > 0:
        env[n_sound:] = np.linspace(1, 0, n_rel)
    return env


def rhodes(f, dur, vel, soft=False):
    n_rel = int(0.08 * SR)
    n = int(dur * SR)
    t = np.arange(n + n_rel) / SR
    index = (1.2 if soft else 2.0) * vel * np.exp(-t / 0.25)
    y = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * f * t))
    y += 0.12 * np.sin(2 * np.pi * 7 * f * t) * np.exp(-t / 0.03)       # tine "bark"
    env = np.minimum(t / 0.003, 1) * np.exp(-t / 1.4) * _release(n, n_rel)
    return vel * y * env


def vibes(f, dur, vel):
    n = int((dur + 0.5) * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / 0.12)
    trem = 1 + 0.25 * np.sin(2 * np.pi * 5.5 * t)
    env = np.minimum(t / 0.002, 1) * np.exp(-t / 1.3)
    damp = np.ones(n)
    k = int(dur * SR)
    damp[k:] = np.exp(-np.arange(n - k) / (0.12 * SR))
    return vel * y * trem * env * damp


def sax(f, dur, vel):
    n_rel = int(0.06 * SR)
    n = int(dur * SR)
    t = np.arange(n + n_rel) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * t) * np.minimum(t / 0.3, 1)
    ph = np.cumsum(f * vib / SR) % 1.0
    y = 2 * ph - 1 + 0.4 * np.sin(2 * np.pi * ph)
    b, a = butter(2, min(0.95, (f * 4 + 800) / (SR / 2)))
    y = lfilter(b, a, y)
    env = np.minimum(t / 0.025, 1) * (0.85 + 0.15 * np.exp(-t / 0.1)) * _release(n, n_rel)
    return 0.8 * vel * y * env


def bass(f, dur, vel):
    n_rel = int(0.05 * SR)
    n = int(dur * SR)
    t = np.arange(n + n_rel) / SR
    y = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(4 * np.pi * f * t) + 0.15 * np.sin(6 * np.pi * f * t)
    env = np.minimum(t / 0.004, 1) * (0.35 + 0.65 * np.exp(-t / 0.18)) * _release(n, n_rel)
    return vel * y * env


@lru_cache(maxsize=2)
def _ride_sample():
    rng = np.random.default_rng(5)
    n = int(1.2 * SR)
    t = np.arange(n) / SR
    y = sum(np.sin(2 * np.pi * fr * t + rng.uniform(0, 6.28)) for fr in (3150, 4370, 5210, 6230, 7820, 9310))
    b, a = butter(2, 6000 / (SR / 2), "high")
    noise = lfilter(b, a, rng.uniform(-1, 1, n))
    return (0.07 * y + 0.8 * noise) * np.exp(-t / 0.35) * np.minimum(t / 0.001, 1)


@lru_cache(maxsize=2)
def _hat_sample():
    rng = np.random.default_rng(6)
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    b, a = butter(2, 7000 / (SR / 2), "high")
    return lfilter(b, a, rng.uniform(-1, 1, n)) * np.exp(-t / 0.025)


def _add(buf, start_s, sig):
    i = int(start_s * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


def render(
    melody: List[Tuple[float, float, int]],
    backing: List[Event],
    total_beats: int,
    tempo: float,
    swing: float,
    lead: str = "rhodes",
    volumes: Dict[str, float] = None,
) -> np.ndarray:
    vol = {"lead": 0.9, "bass": 0.8, "comp": 0.5, "drums": 0.5}
    if volumes:
        vol.update(volumes)
    spb = 60.0 / tempo
    length = total_beats * spb + 2.0
    out = np.zeros(int(length * SR))

    def t_of(beat):
        return swing_time(beat, swing) * spb

    synth = {"rhodes": rhodes, "vibes": vibes, "sax": sax}.get(lead, rhodes)
    for start, dur, pitch in melody:
        s, e = t_of(start), t_of(start + dur)
        _add(out, s, vol["lead"] * 0.5 * synth(_hz(pitch), max(0.05, e - s - 0.01), 0.9))

    ride, hat = _ride_sample(), _hat_sample()
    for ev in backing:
        s, e = t_of(ev.start), t_of(ev.start + ev.dur)
        if ev.part == BASS:
            _add(out, s, vol["bass"] * 0.55 * bass(_hz(ev.pitch), max(0.05, e - s - 0.02), ev.vel))
        elif ev.part == COMP:
            _add(out, s, vol["comp"] * 0.25 * rhodes(_hz(ev.pitch), max(0.05, e - s - 0.02), ev.vel, soft=True))
        elif ev.part == RIDE:
            _add(out, s, vol["drums"] * 0.35 * ev.vel * ride)
        elif ev.part == HAT:
            _add(out, s, vol["drums"] * 0.3 * ev.vel * hat)

    peak = np.max(np.abs(out))
    return 0.95 * out / peak if peak > 0 else out
