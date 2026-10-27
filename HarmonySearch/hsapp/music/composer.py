"""Jazz melody composition as a Harmony Search problem.

Encoding
--------
The melody is a grid of swung eighth notes ("slots"): 8 slots per 4/4 bar.
Each slot is one discrete decision variable with value

    0 .. P-1  -> start a note with pitch ``low + value``   (P = high - low + 1)
    P         -> HOLD: keep sounding the previous note
    P + 1     -> REST

Pitch adjustment moves a pitch up/down by a few semitones (bw is a fraction
of the pitch range), which is literally what a musician does when adjusting
a note. HOLD and REST tokens are never pitch-adjusted.

Fitness
-------
A weighted average of music-theory criteria, each scored in [0, 1].
The weights are dials in the UI. Fitness is maximised.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

from ..hs import Variable
from .theory import Chord, total_beats

SLOTS_PER_BEAT = 2
SLOTS_PER_BAR = 8

CRITERIA = ("harmony", "scale", "smooth", "contour", "density", "syncopation", "phrasing", "motif", "resolution")
DEFAULT_WEIGHTS = {
    "harmony": 3.0,
    "scale": 2.0,
    "smooth": 2.0,
    "contour": 1.0,
    "density": 1.5,
    "syncopation": 1.0,
    "phrasing": 1.0,
    "motif": 1.0,
    "resolution": 1.5,
}

# note roles (used to colour the piano roll)
ROLE_CHORD, ROLE_TENSION, ROLE_SCALE, ROLE_APPROACH, ROLE_OUTSIDE = range(5)


@dataclass
class Note:
    start: int     # slot
    length: int    # slots
    pitch: int     # MIDI


@dataclass
class MelodyProblem:
    chords: List[Chord]
    low: int = 60
    high: int = 81
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    target_density: float = 5.0        # note onsets per bar
    target_syncopation: float = 0.4    # fraction of onsets on off-beats
    p_rest: float = 0.12               # random selection: probability of a rest
    p_hold: float = 0.25               # random selection: probability of a hold

    def __post_init__(self):
        self.P = self.high - self.low + 1
        self.HOLD = self.P
        self.REST = self.P + 1
        self.n_slots = total_beats(self.chords) * SLOTS_PER_BEAT
        self.n_bars = int(np.ceil(self.n_slots / SLOTS_PER_BAR))
        self.slot_chord = np.zeros(self.n_slots, dtype=int)
        s = 0
        for i, c in enumerate(self.chords):
            self.slot_chord[s:s + c.beats * SLOTS_PER_BEAT] = i
            s += c.beats * SLOTS_PER_BEAT
        self._tones = [c.tone_pcs() for c in self.chords]
        self._scale = [c.scale_pcs() for c in self.chords]
        self._tens = [c.tension_pcs() for c in self.chords]

    # ------------------------------------------------------------ HS interface
    def slot_name(self, i: int) -> str:
        bar, pos = divmod(i, SLOTS_PER_BAR)
        beat, off = divmod(pos, 2)
        return f"{bar + 1}.{beat + 1}{'&' if off else ''}"

    def variables(self) -> List[Variable]:
        P, HOLD, REST = self.P, self.HOLD, self.REST
        p_rest, p_hold = self.p_rest, self.p_hold

        def sample(rng):
            r = rng.random()
            if r < p_rest:
                return REST
            if r < p_rest + p_hold:
                return HOLD
            return int(rng.integers(P))

        def adjust(value, bw_frac, rng):
            if value >= P:          # HOLD / REST are not pitches
                return value
            steps = max(1, int(round(bw_frac * P)))
            delta = int(rng.integers(1, steps + 1)) * (1 if rng.random() < 0.5 else -1)
            return float(np.clip(value + delta, 0, P - 1))

        return [Variable(self.slot_name(i), 0, REST, discrete=True, sample=sample, adjust=adjust)
                for i in range(self.n_slots)]

    def token_label(self, v: float) -> str:
        from .theory import note_name

        v = int(v)
        if v == self.HOLD:
            return "—"
        if v == self.REST:
            return "·"
        return note_name(self.low + v)

    # ---------------------------------------------------------------- decoding
    def decode(self, x) -> List[Note]:
        notes: List[Note] = []
        cur = None
        for i, v in enumerate(np.asarray(x, dtype=int)):
            if v < self.P:
                cur = Note(i, 1, self.low + int(v))
                notes.append(cur)
            elif v == self.HOLD and cur is not None:
                cur.length += 1
            else:
                cur = None
        return notes

    def role(self, note: Note, next_note: Note = None) -> int:
        ci = self.slot_chord[note.start]
        pc = note.pitch % 12
        if pc in self._tones[ci]:
            return ROLE_CHORD
        if pc in self._tens[ci]:
            return ROLE_TENSION
        if pc in self._scale[ci]:
            return ROLE_SCALE
        if next_note is not None and abs(next_note.pitch - note.pitch) == 1 and next_note.start - (note.start + note.length) <= 1:
            nci = self.slot_chord[next_note.start]
            if next_note.pitch % 12 in self._tones[nci] or next_note.pitch % 12 in self._scale[nci]:
                return ROLE_APPROACH
        return ROLE_OUTSIDE

    # ----------------------------------------------------------------- fitness
    def components(self, x) -> Dict[str, float]:
        notes = self.decode(x)
        if len(notes) < 2:
            return {k: 0.0 for k in CRITERIA}
        n = len(notes)
        pitches = np.array([nt.pitch for nt in notes])
        starts = np.array([nt.start for nt in notes])
        roles = [self.role(notes[i], notes[i + 1] if i + 1 < n else None) for i in range(n)]

        # 1. harmony: notes on the beat should be chord tones (tensions are OK too)
        on_beat = [i for i in range(n) if starts[i] % 2 == 0]
        role_score = {ROLE_CHORD: 1.0, ROLE_TENSION: 0.6, ROLE_SCALE: 0.25, ROLE_APPROACH: 0.2, ROLE_OUTSIDE: 0.0}
        harmony = float(np.mean([role_score[roles[i]] for i in on_beat])) if on_beat else 0.3

        # 2. scale: every note inside the chord scale, or a chromatic approach note
        scale_score = {ROLE_CHORD: 1.0, ROLE_TENSION: 1.0, ROLE_SCALE: 1.0, ROLE_APPROACH: 0.9, ROLE_OUTSIDE: 0.0}
        scale = float(np.mean([scale_score[r] for r in roles]))

        # 3. smooth: mostly steps, few big leaps, leaps followed by a step back (gap fill)
        iv = np.diff(pitches)
        a = np.abs(iv)
        sm = np.select([a == 0, a <= 2, a <= 4, a <= 7, a <= 12], [0.5, 1.0, 0.85, 0.5, 0.2], 0.0).astype(float)
        for i in range(1, len(iv)):
            if a[i - 1] >= 5 and a[i] <= 2 and a[i] > 0 and np.sign(iv[i]) != np.sign(iv[i - 1]):
                sm[i - 1] = max(sm[i - 1], 0.8)
        smooth = float(np.mean(sm))

        # 4. contour: some direction changes (arches), no endless scale runs
        d = np.sign(iv[iv != 0])
        if len(d) >= 2:
            changes = np.mean(d[1:] != d[:-1])
            ca = 1.0 - min(1.0, abs(changes - 0.4) / 0.6)
            run, longest = 1, 1
            for i in range(1, len(d)):
                run = run + 1 if d[i] == d[i - 1] else 1
                longest = max(longest, run)
            cb = 1.0 if longest <= 6 else max(0.0, 1.0 - (longest - 6) / 6.0)
            contour = 0.6 * ca + 0.4 * cb
        else:
            contour = 0.0

        # 5. density: onsets per bar close to the target
        counts = np.bincount(starts // SLOTS_PER_BAR, minlength=self.n_bars)[: self.n_bars]
        t = max(self.target_density, 0.5)
        density = float(np.mean(np.clip(1.0 - np.abs(counts - t) / t, 0, 1)))

        # 6. syncopation: fraction of onsets on the "and"
        f_off = float(np.mean(starts % 2 == 1))
        ts = self.target_syncopation
        syncopation = 1.0 - abs(f_off - ts) / max(ts, 1 - ts)

        # 7. phrasing: phrases of ~1-2.5 bars separated by rests (players must breathe)
        phrases: List[List[int]] = [[0]]
        for i in range(1, n):
            gap = notes[i].start - (notes[i - 1].start + notes[i - 1].length)
            if gap >= 2:
                phrases.append([i])
            else:
                phrases[-1].append(i)
        ps = []
        for ph in phrases:
            first, last = notes[ph[0]], notes[ph[-1]]
            bars = (last.start + last.length - first.start) / SLOTS_PER_BAR
            if len(ph) < 2:
                s = 0.3
            elif bars < 0.75:
                s = 0.5 + 0.5 * bars / 0.75
            elif bars <= 2.5:
                s = 1.0
            else:
                s = max(0.0, 1.0 - (bars - 2.5) / 2.0)
            ps.append(s)
        phrasing = float(np.mean(ps))
        gaps = [notes[i].start - (notes[i - 1].start + notes[i - 1].length) for i in range(1, n)]
        long_silences = sum(1 for g in gaps if g > 12) + (1 if notes[0].start > 12 else 0)
        phrasing *= 0.8 ** long_silences

        # 8. motif: bars 1-2, 3-4, ... echo each other (rhythm + melodic direction)
        by_bar: List[List[Note]] = [[] for _ in range(self.n_bars)]
        for nt in notes:
            by_bar[nt.start // SLOTS_PER_BAR].append(nt)
        sims = []
        for b in range(0, self.n_bars - 1, 2):
            A, B = by_bar[b], by_bar[b + 1]
            if not A or not B:
                sims.append(0.0)
                continue
            ra = {nt.start % SLOTS_PER_BAR for nt in A}
            rb = {nt.start % SLOTS_PER_BAR for nt in B}
            jac = len(ra & rb) / len(ra | rb)
            da = np.sign(np.diff([nt.pitch for nt in A]))
            db = np.sign(np.diff([nt.pitch for nt in B]))
            m = min(len(da), len(db))
            dirs = float(np.mean(da[:m] == db[:m])) if m else 0.5
            sims.append(0.5 * jac + 0.5 * dirs)
        motif = float(np.mean(sims)) if sims else 0.5

        # 9. resolution: end on root/3rd, held; phrases end on chord tones
        last = notes[-1]
        lc = self.chords[self.slot_chord[last.start]]
        rel = (last.pitch - lc.root) % 12
        if rel in (0, lc.q.tones[1]):
            fin = 1.0
        elif last.pitch % 12 in lc.tone_pcs():
            fin = 0.7
        elif last.pitch % 12 in lc.scale_pcs():
            fin = 0.3
        else:
            fin = 0.0
        if last.length < 2:
            fin *= 0.6
        if last.start + last.length < self.n_slots - SLOTS_PER_BAR:
            fin *= 0.7
        ends = [roles[ph[-1]] == ROLE_CHORD for ph in phrases]
        resolution = 0.5 * fin + 0.5 * float(np.mean(ends))

        return {
            "harmony": harmony,
            "scale": scale,
            "smooth": smooth,
            "contour": float(contour),
            "density": density,
            "syncopation": float(syncopation),
            "phrasing": phrasing,
            "motif": motif,
            "resolution": resolution,
        }

    def score(self, comps: Dict[str, float]) -> float:
        wsum = sum(self.weights.get(k, 0) for k in CRITERIA)
        if wsum <= 0:
            return 0.0
        return sum(self.weights.get(k, 0) * comps[k] for k in CRITERIA) / wsum

    def __call__(self, x) -> float:
        return self.score(self.components(x))

    def to_beats(self, notes: List[Note]) -> List[Tuple[float, float, int]]:
        """(start_beat, duration_beats, midi) for rendering/MIDI."""
        return [(nt.start / SLOTS_PER_BEAT, nt.length / SLOTS_PER_BEAT, nt.pitch) for nt in notes]
