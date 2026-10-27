"""Small DSP toolkit: STFT/ISTFT, mel filterbank, loudness envelope and YIN pitch detection.

Only numpy/scipy are used so the app installs cleanly on Windows and Apple Silicon.
"""

from __future__ import annotations

import numpy as np

SR = 22050          # sample rate used for analysis and for the matching synth
N_FFT = 1024
HOP = 256
N_MELS = 64

_WINDOW = np.hanning(N_FFT + 1)[:-1].astype(np.float64)


def frame_count(n_samples: int) -> int:
    return 1 + max(0, n_samples - 1) // HOP


def stft(x: np.ndarray) -> np.ndarray:
    """Complex STFT, shape (frames, N_FFT//2+1). Frames are centred (padded by N_FFT//2)."""
    pad = N_FFT // 2
    xp = np.pad(x, (pad, pad + N_FFT))
    n_frames = frame_count(len(x))
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = xp[idx] * _WINDOW
    return np.fft.rfft(frames, axis=1)


def istft(X: np.ndarray, length: int) -> np.ndarray:
    """Inverse of :func:`stft` (weighted overlap-add)."""
    frames = np.fft.irfft(X, n=N_FFT, axis=1) * _WINDOW
    pad = N_FFT // 2
    total = HOP * (len(frames) - 1) + N_FFT
    out = np.zeros(total)
    norm = np.zeros(total)
    w2 = _WINDOW ** 2
    for i, fr in enumerate(frames):
        s = i * HOP
        out[s:s + N_FFT] += fr
        norm[s:s + N_FFT] += w2
    out /= np.maximum(norm, 1e-8)
    return out[pad:pad + length]


def hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def mel_to_hz(m):
    return 700.0 * (10 ** (np.asarray(m) / 2595.0) - 1.0)


def _mel_filterbank(n_mels=N_MELS, fmin=40.0, fmax=SR / 2):
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / SR)
    edges = mel_to_hz(np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels + 2))
    fb = np.zeros((len(freqs), n_mels))
    for m in range(n_mels):
        lo, c, hi = edges[m], edges[m + 1], edges[m + 2]
        up = (freqs - lo) / max(c - lo, 1e-9)
        down = (hi - freqs) / max(hi - c, 1e-9)
        fb[:, m] = np.clip(np.minimum(up, down), 0, None)
    fb /= np.maximum(fb.sum(axis=0, keepdims=True), 1e-9)
    return fb


MEL_FB = _mel_filterbank()
MEL_CENTERS_HZ = mel_to_hz(np.linspace(hz_to_mel(40.0), hz_to_mel(SR / 2), N_MELS + 2))[1:-1]
FFT_FREQS = np.fft.rfftfreq(N_FFT, 1.0 / SR)

DB_FLOOR = 80.0


def power_to_rel_db(p: np.ndarray, ref: float | None = None) -> np.ndarray:
    """Power -> dB relative to the maximum (0 dB at max, floored at -DB_FLOOR)."""
    ref = float(np.max(p)) if ref is None else ref
    db = 10.0 * np.log10(np.maximum(p, 1e-12) / max(ref, 1e-12))
    return np.maximum(db, -DB_FLOOR)


def mel_db(mag: np.ndarray) -> np.ndarray:
    """Magnitude spectrogram -> mel spectrogram in relative dB, shape (frames, N_MELS)."""
    return power_to_rel_db((mag ** 2) @ MEL_FB)


def envelope_db(mag: np.ndarray) -> np.ndarray:
    """Per-frame loudness (relative dB) from a magnitude spectrogram."""
    return power_to_rel_db(np.sum(mag ** 2, axis=1))


def yin_pitch(x: np.ndarray, sr: int = SR, fmin=50.0, fmax=1500.0, threshold=0.15):
    """Estimate the dominant pitch with the YIN algorithm (de Cheveigné & Kawahara, 2002).

    Returns (frequency_hz or None, confidence 0..1).
    """
    frame = 2048
    if len(x) < frame:
        x = np.pad(x, (0, frame - len(x)))
    tau_min = max(2, int(sr / fmax))
    tau_max = min(frame // 2, int(sr / fmin))
    hop = 512
    rms = np.array([np.sqrt(np.mean(x[i:i + frame] ** 2)) for i in range(0, len(x) - frame + 1, hop)])
    if len(rms) == 0 or rms.max() <= 0:
        return None, 0.0
    starts = [i * hop for i, r in enumerate(rms) if r > 0.3 * rms.max()]
    estimates, confidences = [], []
    for s in starts[:60]:
        fr = x[s:s + frame] - np.mean(x[s:s + frame])
        w = frame // 2
        # difference function d(tau) = sum_{j<w} (x_j - x_{j+tau})^2, via FFT cross-correlation
        nfft = 2 * frame
        r = np.fft.irfft(np.fft.rfft(fr, nfft) * np.conj(np.fft.rfft(fr[:w], nfft)), nfft)[:w + 1]
        sq = np.concatenate(([0.0], np.cumsum(fr ** 2)))
        taus = np.arange(w + 1)
        e0 = sq[w]
        e_tau = sq[taus + w] - sq[taus]
        d = e0 + e_tau - 2 * r
        d[0] = 0.0
        cmnd = np.ones(w + 1)
        cs = np.cumsum(d[1:])
        cmnd[1:] = d[1:] * taus[1:] / np.maximum(cs, 1e-12)
        seg = cmnd[tau_min:tau_max]
        below = np.where(seg < threshold)[0]
        if len(below):
            t = below[0]
            while t + 1 < len(seg) and seg[t + 1] < seg[t]:
                t += 1
        else:
            t = int(np.argmin(seg))
        tau = t + tau_min
        conf = 1.0 - float(cmnd[tau])
        if 1 <= tau < w:
            a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
            denom = a - 2 * b + c
            shift = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
            tau = tau + float(np.clip(shift, -1, 1))
        estimates.append(sr / tau)
        confidences.append(conf)
    if not estimates:
        return None, 0.0
    conf = float(np.median(confidences))
    return float(np.median(estimates)), max(0.0, min(1.0, conf))


def hz_to_midi(f: float) -> float:
    return 69.0 + 12.0 * np.log2(f / 440.0)


def midi_to_hz(m):
    return 440.0 * 2.0 ** ((np.asarray(m) - 69.0) / 12.0)


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_name(m: float) -> str:
    n = int(round(m))
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"
