"""Minimal jazz harmony: chord qualities, chord scales and progressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def note_name(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


@dataclass(frozen=True)
class Quality:
    symbol: str
    tones: Tuple[int, ...]       # chord tones (1-3-5-7) as semitones above the root
    scale: Tuple[int, ...]       # chord scale used for "inside" notes
    tensions: Tuple[int, ...]    # available tensions (9, 11, 13 ...)


QUALITIES: Dict[str, Quality] = {
    "maj7": Quality("maj7", (0, 4, 7, 11), (0, 2, 4, 5, 7, 9, 11), (2, 9)),             # Ionian
    "6": Quality("6", (0, 4, 7, 9), (0, 2, 4, 5, 7, 9, 11), (2,)),                     # Ionian
    "m7": Quality("m7", (0, 3, 7, 10), (0, 2, 3, 5, 7, 9, 10), (2, 5, 9)),            # Dorian
    "7": Quality("7", (0, 4, 7, 10), (0, 2, 4, 5, 7, 9, 10), (2, 9)),                 # Mixolydian
    "m7b5": Quality("m7♭5", (0, 3, 6, 10), (0, 2, 3, 5, 6, 8, 10), (2, 5, 8)),        # Locrian #2
    "7b9": Quality("7♭9", (0, 4, 7, 10), (0, 1, 3, 4, 6, 7, 9, 10), (1, 3, 9)),       # half-whole diminished
    "m6": Quality("m6", (0, 3, 7, 9), (0, 2, 3, 5, 7, 9, 11), (2, 5)),                # melodic minor
    "dim7": Quality("°7", (0, 3, 6, 9), (0, 2, 3, 5, 6, 8, 9, 11), (2, 5)),           # whole-half diminished
}


@dataclass(frozen=True)
class Chord:
    root: int        # pitch class 0..11
    quality: str
    beats: int       # duration in beats (4/4)

    @property
    def q(self) -> Quality:
        return QUALITIES[self.quality]

    @property
    def symbol(self) -> str:
        return NOTE_NAMES[self.root] + self.q.symbol

    def tone_pcs(self):
        return {(self.root + i) % 12 for i in self.q.tones}

    def scale_pcs(self):
        return {(self.root + i) % 12 for i in self.q.scale}

    def tension_pcs(self):
        return {(self.root + i) % 12 for i in self.q.tensions}


# Progressions are written relative to the key root: (semitones, quality, beats).
PROGRESSIONS: Dict[str, dict] = {
    "ii-V-I": {
        "default_key": 0,   # C
        "chords": [(2, "m7", 4), (7, "7", 4), (0, "maj7", 4), (0, "maj7", 4)],
    },
    "ii-V-i minor": {
        "default_key": 0,   # C minor
        "chords": [(2, "m7b5", 4), (7, "7b9", 4), (0, "m6", 4), (0, "m6", 4)],
    },
    "Jazz blues": {
        "default_key": 5,   # F
        "chords": [
            (0, "7", 4), (5, "7", 4), (0, "7", 4), (7, "m7", 2), (0, "7", 2),
            (5, "7", 4), (6, "dim7", 4), (0, "7", 4), (9, "7b9", 4),
            (2, "m7", 4), (7, "7", 4), (0, "7", 2), (9, "7b9", 2), (2, "m7", 2), (7, "7", 2),
        ],
    },
    "Autumn Leaves (A)": {
        "default_key": 7,   # G minor
        "chords": [
            (5, "m7", 4), (10, "7", 4), (3, "maj7", 4), (8, "maj7", 4),
            (2, "m7b5", 4), (7, "7b9", 4), (0, "m6", 4), (0, "m6", 4),
        ],
    },
    "Rhythm changes (A)": {
        "default_key": 10,  # Bb
        "chords": [
            (0, "maj7", 2), (9, "7", 2), (2, "m7", 2), (7, "7", 2),
            (4, "m7", 2), (9, "7", 2), (2, "m7", 2), (7, "7", 2),
            (7, "m7", 2), (0, "7", 2), (5, "maj7", 2), (6, "dim7", 2),
            (2, "m7", 2), (7, "7", 2), (2, "m7", 2), (7, "7", 2),
        ],
    },
    "Modal vamp (Dorian)": {
        "default_key": 2,   # D
        "chords": [(0, "m7", 4)] * 8,
    },
}


def build_progression(name: str, key: int, repeats: int = 1) -> List[Chord]:
    spec = PROGRESSIONS[name]
    one = [Chord((key + off) % 12, q, beats) for off, q, beats in spec["chords"]]
    return one * max(1, repeats)


def total_beats(chords: List[Chord]) -> int:
    return sum(c.beats for c in chords)
