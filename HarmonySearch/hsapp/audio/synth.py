"""A small subtractive synthesizer whose knobs are tuned by Harmony Search.

Signal flow::

    OSC1 (sine->tri->saw->square morph) --+
                                          +-- mix --+-- noise mix -- AMP ADSR -- resonant LOW-PASS -- out
    OSC2 (same, detuned in semitones) ----+                                      ^
                                                                                 |
                                              FILTER ENVELOPE (cutoff * 2^(amount*env))

Every knob lives in [0, 1] (its position on the dial); ``SynthParam`` maps a
knob position to a physical value (Hz, seconds, ...). Harmony Search works
directly on knob positions, so "HS turns the knobs" is literally true.

The low-pass filter is applied per STFT frame (a time-varying spectral
filter). The fitness function compares magnitude spectrograms, so it uses
exactly the spectrogram you hear when the result is played back.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List

import numpy as np

from . import dsp
from .dsp import SR


@dataclass(frozen=True)
class SynthParam:
    key: str
    lo: float
    hi: float
    default: float          # physical default value
    scale: str = "lin"      # "lin" or "log"
    unit: str = ""
    decimals: int = 2

    def to_value(self, knob: float) -> float:
        k = float(np.clip(knob, 0.0, 1.0))
        if self.scale == "log":
            return float(self.lo * (self.hi / self.lo) ** k)
        return float(self.lo + (self.hi - self.lo) * k)

    def to_knob(self, value: float) -> float:
        if self.scale == "log":
            v = max(float(value), self.lo)
            return float(np.clip(np.log(v / self.lo) / np.log(self.hi / self.lo), 0, 1))
        return float(np.clip((value - self.lo) / (self.hi - self.lo), 0, 1))

    @property
    def default_knob(self) -> float:
        return self.to_knob(self.default)

    def format(self, value: float) -> str:
        if self.key == "pitch":
            return f"{dsp.midi_name(value)} ({dsp.midi_to_hz(value):.0f} Hz)"
        if self.key in ("wave1", "wave2"):
            names = ["sin", "tri", "saw", "sqr"]
            i = int(np.clip(np.floor(value), 0, 2))
            f = value - i
            if f < 0.08:
                return names[i]
            if f > 0.92:
                return names[i + 1]
            return f"{names[i]}>{names[i + 1]}"
        if self.unit == "Hz" and value >= 1000:
            return f"{value / 1000:.1f} kHz"
        if self.unit == "s" and value < 1:
            return f"{value * 1000:.0f} ms"
        return f"{value:.{self.decimals}f}{(' ' + self.unit) if self.unit else ''}"


PARAMS: List[SynthParam] = [
    SynthParam("pitch", 24, 96, 60, unit="", decimals=1),
    SynthParam("wave1", 0, 3, 2),
    SynthParam("wave2", 0, 3, 3),
    SynthParam("detune", -12, 12, 0.1, unit="st"),
    SynthParam("mix", 0, 1, 0.3),
    SynthParam("noise", 0, 1, 0.0),
    SynthParam("cutoff", 40, 10000, 1500, scale="log", unit="Hz", decimals=0),
    SynthParam("resonance", 0, 0.95, 0.2),
    SynthParam("env_amt", 0, 5, 1.5, unit="oct", decimals=1),
    SynthParam("f_decay", 0.01, 4, 0.4, scale="log", unit="s"),
    SynthParam("attack", 0.001, 2, 0.01, scale="log", unit="s"),
    SynthParam("decay", 0.01, 4, 0.5, scale="log", unit="s"),
    SynthParam("sustain", 0, 1, 0.6),
    SynthParam("release", 0.01, 4, 0.3, scale="log", unit="s"),
    SynthParam("gate", 0.02, 1, 0.7, unit="", decimals=2),
    SynthParam("vib_depth", 0, 1, 0.0, unit="st"),
    SynthParam("vib_rate", 2, 9, 5.5, unit="Hz", decimals=1),
]
PARAM_BY_KEY: Dict[str, SynthParam] = {p.key: p for p in PARAMS}
KEYS = [p.key for p in PARAMS]


def default_knobs() -> Dict[str, float]:
    return {p.key: p.default_knob for p in PARAMS}


def knobs_to_values(knobs: Dict[str, float]) -> Dict[str, float]:
    return {k: PARAM_BY_KEY[k].to_value(v) for k, v in knobs.items()}


@lru_cache(maxsize=8)
def _noise(n: int) -> np.ndarray:
    # fixed seed: the same knobs must always give the same sound (deterministic fitness)
    return np.random.default_rng(1234).uniform(-1, 1, n)


def _polyblep(t: np.ndarray, dt: np.ndarray) -> np.ndarray:
    out = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    out[m] = x + x - x * x - 1.0
    m = t > 1.0 - dt
    x = (t[m] - 1.0) / dt[m]
    out[m] = x * x + x + x + 1.0
    return out


def _shape(idx: int, ph: np.ndarray, dt: np.ndarray) -> np.ndarray:
    if idx == 0:
        return np.sin(2 * np.pi * ph)
    if idx == 1:
        return 1.0 - 4.0 * np.abs(ph - 0.5)
    if idx == 2:
        return 2.0 * ph - 1.0 - _polyblep(ph, dt)
    sq = np.where(ph < 0.5, 1.0, -1.0)
    return sq + _polyblep(ph, dt) - _polyblep((ph + 0.5) % 1.0, dt)


def _oscillator(wave: float, freq: np.ndarray) -> np.ndarray:
    dt = np.clip(freq / SR, 1e-6, 0.49)
    ph = np.cumsum(dt) % 1.0
    i = int(np.clip(np.floor(wave), 0, 2))
    f = float(wave - i)
    if f < 1e-3:
        return _shape(i, ph, dt)
    if f > 1 - 1e-3:
        return _shape(i + 1, ph, dt)
    return (1 - f) * _shape(i, ph, dt) + f * _shape(i + 1, ph, dt)


def adsr(t: np.ndarray, a: float, d: float, s: float, r: float, gate: float) -> np.ndarray:
    def held(tt):
        return np.where(tt < a, tt / a, s + (1 - s) * np.exp(-np.maximum(tt - a, 0.0) / (d / 4.0)))

    env = held(t)
    level = float(held(np.array([gate]))[0])
    after = t >= gate
    env[after] = level * np.exp(-(t[after] - gate) / (r / 4.0))
    return env


def _render(knobs: Dict[str, float], n: int):
    """Return (complex STFT of the unfiltered voice, filter magnitude response per frame)."""
    v = knobs_to_values(knobs)
    t = np.arange(n) / SR
    duration = n / SR
    freq = float(dsp.midi_to_hz(v["pitch"]))
    if v["vib_depth"] > 1e-3:
        fvec = freq * 2.0 ** (v["vib_depth"] * np.sin(2 * np.pi * v["vib_rate"] * t) / 12.0)
    else:
        fvec = np.full(n, freq)
    src = _oscillator(v["wave1"], fvec)
    if v["mix"] > 1e-3:
        src = (1 - v["mix"]) * src + v["mix"] * _oscillator(v["wave2"], fvec * 2.0 ** (v["detune"] / 12.0))
    if v["noise"] > 1e-3:
        src = (1 - v["noise"]) * src + v["noise"] * 0.8 * _noise(n)
    gate = max(0.02, v["gate"] * duration)
    src = src * adsr(t, v["attack"], v["decay"], v["sustain"], v["release"], gate)

    X = dsp.stft(src)
    tf = np.arange(X.shape[0]) * dsp.HOP / SR
    fenv = np.exp(-tf / (v["f_decay"] / 3.0))
    fc = np.clip(v["cutoff"] * 2.0 ** (v["env_amt"] * fenv), 20.0, 0.45 * SR).astype(np.float32)[:, None]
    q = 0.707 + v["resonance"] * 11.0
    # 2-pole resonant low-pass: |H| = 1 / sqrt((1 - r^2)^2 + (r/Q)^2), r = f / fc
    r2 = (_FREQS32[None, :] / fc) ** 2
    h = 1.0 / np.sqrt((1.0 - r2) ** 2 + r2 / np.float32(q * q))
    return X, h


_FREQS32 = dsp.FFT_FREQS.astype(np.float32)


def render_spectrogram(knobs: Dict[str, float], n: int) -> np.ndarray:
    """Complex STFT of the synth output for ``n`` samples."""
    X, h = _render(knobs, n)
    return X * h


def render_magnitude(knobs: Dict[str, float], n: int) -> np.ndarray:
    """Magnitude STFT of the synth output (what the fitness function compares)."""
    X, h = _render(knobs, n)
    return np.abs(X).astype(np.float32) * h


def render_audio(knobs: Dict[str, float], n: int) -> np.ndarray:
    y = dsp.istft(render_spectrogram(knobs, n), n)
    peak = np.max(np.abs(y))
    return (0.9 * y / peak) if peak > 0 else y


def random_knobs(rng: np.random.Generator) -> Dict[str, float]:
    """A random but musically sensible patch (used for the 'known target' demo)."""
    k = {p.key: float(rng.random()) for p in PARAMS}
    k["pitch"] = PARAM_BY_KEY["pitch"].to_knob(rng.integers(45, 73))
    k["gate"] = float(rng.uniform(0.35, 0.8))
    k["noise"] = float(rng.uniform(0, 0.4)) if rng.random() < 0.5 else 0.0
    k["vib_depth"] = float(rng.uniform(0, 0.4)) if rng.random() < 0.4 else 0.0
    # osc 2 at unison, a fifth or an octave keeps the pitch unambiguous
    det = PARAM_BY_KEY["detune"]
    k["detune"] = det.to_knob(float(rng.choice([0, 0, 7, 12, -12])) + float(rng.uniform(-0.15, 0.15)))
    k["cutoff"] = float(rng.uniform(0.25, 0.9))
    k["attack"] = float(rng.uniform(0.0, 0.6))
    return k
