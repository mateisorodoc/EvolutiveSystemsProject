"""Rule-based rhythm section (not evolved): walking bass, piano comping and ride cymbal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .theory import Chord

BASS, COMP, RIDE, HAT = "bass", "comp", "ride", "hat"


@dataclass
class Event:
    start: float      # beats (straight time; swing is applied when rendering)
    dur: float        # beats
    pitch: int        # MIDI (for drums: GM drum note)
    vel: float        # 0..1
    part: str


def _nearest(pc: int, ref: int, lo: int, hi: int) -> int:
    cands = [p for p in range(lo, hi + 1) if p % 12 == pc]
    return min(cands, key=lambda p: abs(p - ref))


def walking_bass(chords: List[Chord], rng: np.random.Generator) -> List[Event]:
    lo, hi = 33, 52                     # A1 .. E3
    ev: List[Event] = []
    beat = 0.0
    prev = 41
    for ci, ch in enumerate(chords):
        nxt = chords[(ci + 1) % len(chords)]
        root = _nearest(ch.root, prev, lo, hi)
        target = _nearest(nxt.root, root, lo, hi)
        tones = sorted({p for p in range(lo, hi + 1) if p % 12 in ch.tone_pcs()})
        scale = sorted({p for p in range(lo, hi + 1) if p % 12 in ch.scale_pcs()})
        line = [root]
        for b in range(1, ch.beats):
            cur = line[-1]
            if b == ch.beats - 1:
                # chromatic or scale approach into the next root
                if rng.random() < 0.65:
                    note = target - 1 if abs(target - 1 - cur) <= abs(target + 1 - cur) else target + 1
                else:
                    cands = [p for p in scale if 0 < abs(p - target) <= 2]
                    note = min(cands, key=lambda p: abs(p - cur)) if cands else target - 1
            else:
                direction = np.sign(target - cur) or (1 if rng.random() < 0.5 else -1)
                pool = tones if rng.random() < 0.6 else scale
                cands = [p for p in pool if 0 < (p - cur) * direction <= 5]
                note = int(rng.choice(cands)) if cands else cur + int(direction) * 2
            line.append(int(np.clip(note, lo, hi)))
        for b, p in enumerate(line):
            ev.append(Event(beat + b, 0.95, p, 0.85 if b == 0 else 0.75, BASS))
        prev = line[-1]
        beat += ch.beats
    return ev


_COMP_4 = [[(0, 1.5), (1.5, 0.5)], [(0.5, 1.0), (2.5, 1.0)], [(0, 1.0), (2.5, 1.5)], [(1.5, 1.0), (3.5, 0.5)]]
_COMP_2 = [[(0, 1.0)], [(0.5, 1.0)], [(0, 0.5), (1.5, 0.5)]]


def comping(chords: List[Chord], rng: np.random.Generator) -> List[Event]:
    """Rootless shell voicings (3rd + 7th + a colour tone) in a Charleston-like rhythm."""
    ev: List[Event] = []
    beat = 0.0
    top = 64
    for ch in chords:
        q = ch.q
        pcs = [(ch.root + q.tones[1]) % 12, (ch.root + q.tones[3]) % 12]
        if q.tensions:
            pcs.append((ch.root + q.tensions[0]) % 12)
        third = _nearest(pcs[0], top - 5, 50, 62)
        voicing = [third]
        for pc in pcs[1:]:
            p = voicing[-1] + 1
            while p % 12 != pc:
                p += 1
            voicing.append(p)
        top = voicing[-1]
        patterns = _COMP_4 if ch.beats >= 4 else _COMP_2
        for off, dur in patterns[int(rng.integers(len(patterns)))]:
            if off < ch.beats:
                for p in voicing:
                    ev.append(Event(beat + off, dur, p, 0.55 + 0.1 * rng.random(), COMP))
        beat += ch.beats
    return ev


def drums(total_beats: int) -> List[Event]:
    ev: List[Event] = []
    for b in range(total_beats):
        accent = 0.8 if b % 2 == 1 else 0.65
        ev.append(Event(b, 1.0, 51, accent, RIDE))                 # ride on every beat
        if b % 2 == 1:
            ev.append(Event(b + 0.5, 0.5, 51, 0.5, RIDE))           # "spang-a-lang" skip note
            ev.append(Event(b, 0.5, 44, 0.6, HAT))                  # hi-hat foot on 2 and 4
    return ev


def build(chords: List[Chord], seed: int = 7) -> List[Event]:
    rng = np.random.default_rng(seed)
    total = int(sum(c.beats for c in chords))
    return walking_bass(chords, rng) + comping(chords, rng) + drums(total)
