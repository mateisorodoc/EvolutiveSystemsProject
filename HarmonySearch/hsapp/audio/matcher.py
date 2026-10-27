"""Sound matching problem: find synth knob settings whose sound resembles a target recording."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ..hs import Variable
from . import dsp, synth
from .dsp import SR

MAX_SECONDS = 10.0

# fitness components (keys are also i18n keys "cost.<key>")
COST_KEYS = ("timbre", "envelope", "spectrum")
DEFAULT_COST_WEIGHTS = {"timbre": 1.0, "envelope": 1.0, "spectrum": 1.0}


def prepare_target(x: np.ndarray, sr: int, max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """Mono, resample to SR, trim silence, cap length, normalise peak."""
    from scipy.signal import resample_poly

    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != SR:
        g = np.gcd(int(sr), SR)
        x = resample_poly(x, SR // g, int(sr) // g)
    if len(x) == 0 or np.max(np.abs(x)) == 0:
        return np.zeros(int(0.5 * SR))
    x = x / np.max(np.abs(x))
    # trim leading/trailing silence (below -40 dB of peak, measured on 10 ms blocks)
    blk = int(0.01 * SR)
    nb = max(1, len(x) // blk)
    rms = np.sqrt(np.mean(x[: nb * blk].reshape(nb, blk) ** 2, axis=1))
    loud = np.where(rms > 0.01 * rms.max())[0]
    if len(loud):
        start = max(0, loud[0] * blk - blk)
        end = min(len(x), (loud[-1] + 2) * blk)
        x = x[start:end]
    x = x[: int(max_seconds * SR)]
    # short fades avoid clicks
    f = min(len(x) // 4, int(0.005 * SR))
    if f > 1:
        x[:f] *= np.linspace(0, 1, f)
        x[-f:] *= np.linspace(1, 0, f)
    return 0.9 * x / max(np.max(np.abs(x)), 1e-9)


@dataclass
class TargetFeatures:
    audio: np.ndarray
    mel: np.ndarray
    env: np.ndarray
    spectrum: np.ndarray
    pitch_hz: Optional[float]
    pitch_conf: float

    @property
    def n(self) -> int:
        return len(self.audio)

    @property
    def duration(self) -> float:
        return self.n / SR


def _features(mag: np.ndarray):
    mel = dsp.mel_db(mag)
    env = dsp.envelope_db(mag)
    spectrum = dsp.power_to_rel_db(np.mean((mag ** 2) @ dsp.MEL_FB, axis=0))
    return mel, env, spectrum


def analyse(audio: np.ndarray) -> TargetFeatures:
    mag = np.abs(dsp.stft(audio))
    mel, env, spectrum = _features(mag)
    f0, conf = dsp.yin_pitch(audio)
    return TargetFeatures(audio, mel, env, spectrum, f0, conf)


@dataclass
class MatchProblem:
    """Decision variables + objective for Harmony Search."""

    target: TargetFeatures
    lock_pitch: bool = True
    locked_pitch_knob: float = 0.5
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_COST_WEIGHTS))
    fixed: Dict[str, float] = field(default_factory=dict)   # knobs excluded from the search

    def __post_init__(self):
        self.free_keys: List[str] = [k for k in synth.KEYS if not (k == "pitch" and self.lock_pitch) and k not in self.fixed]

    def variables(self) -> List[Variable]:
        return [Variable(k, 0.0, 1.0) for k in self.free_keys]

    def knobs(self, x: np.ndarray) -> Dict[str, float]:
        k = synth.default_knobs()
        k.update(self.fixed)
        if self.lock_pitch:
            k["pitch"] = self.locked_pitch_knob
        for key, val in zip(self.free_keys, x):
            k[key] = float(val)
        return k

    def components(self, knobs: Dict[str, float]) -> Dict[str, float]:
        mag = synth.render_magnitude(knobs, self.target.n)
        mel, env, spectrum = _features(mag)
        t = self.target
        return {
            "timbre": float(np.mean(np.abs(mel - t.mel))) / dsp.DB_FLOOR,
            "envelope": float(np.mean(np.abs(env - t.env))) / dsp.DB_FLOOR,
            "spectrum": float(np.mean(np.abs(spectrum - t.spectrum))) / dsp.DB_FLOOR,
        }

    def cost_of_knobs(self, knobs: Dict[str, float]) -> float:
        c = self.components(knobs)
        wsum = sum(self.weights.values()) or 1.0
        return sum(self.weights[k] * c[k] for k in COST_KEYS) / wsum

    def __call__(self, x: np.ndarray) -> float:
        return self.cost_of_knobs(self.knobs(x))

    def features_of(self, knobs: Dict[str, float]):
        mag = synth.render_magnitude(knobs, self.target.n)
        return _features(mag)
