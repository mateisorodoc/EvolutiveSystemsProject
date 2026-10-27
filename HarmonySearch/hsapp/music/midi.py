"""Standard MIDI file export (melody, bass, piano and drums on separate tracks)."""

from __future__ import annotations

from typing import List, Tuple

import mido

from .backing import BASS, COMP, HAT, RIDE, Event
from .render import swing_time
from .theory import Chord

TPB = 480
LEAD_PROGRAMS = {"rhodes": 4, "vibes": 11, "sax": 65}   # GM: Electric Piano 1, Vibraphone, Alto Sax


def _track(name, channel, program, notes, tempo=None, chords=None, swing=0.5):
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name", name=name, time=0))
    if tempo is not None:
        tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo), time=0))
        tr.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    if program is not None:
        tr.append(mido.Message("program_change", channel=channel, program=program, time=0))
    msgs = []
    if chords:
        beat = 0
        for c in chords:
            text = c.symbol.replace("♭", "b").replace("°", "dim")   # MIDI text is latin-1
            msgs.append((int(beat * TPB), 0, mido.MetaMessage("marker", text=text)))
            beat += c.beats
    for start, dur, pitch, vel in notes:
        on = int(round(swing_time(start, swing) * TPB))
        off = max(on + 1, int(round(swing_time(start + dur, swing) * TPB)) - 10)
        v = max(1, min(127, int(vel * 127)))
        msgs.append((on, 1, mido.Message("note_on", channel=channel, note=int(pitch), velocity=v)))
        msgs.append((off, 0, mido.Message("note_off", channel=channel, note=int(pitch), velocity=0)))
    msgs.sort(key=lambda m: (m[0], m[1]))
    now = 0
    for t, _, m in msgs:
        tr.append(m.copy(time=t - now))
        now = t
    return tr


def export_midi(
    path: str,
    melody: List[Tuple[float, float, int]],
    backing: List[Event],
    chords: List[Chord],
    tempo: float,
    swing: float,
    lead: str = "rhodes",
):
    mid = mido.MidiFile(ticks_per_beat=TPB)
    mid.tracks.append(_track("Melody (Harmony Search)", 0, LEAD_PROGRAMS.get(lead, 4),
                             [(s, d, p, 0.9) for s, d, p in melody], tempo=tempo, chords=chords, swing=swing))
    mid.tracks.append(_track("Walking bass", 1, 32,
                             [(e.start, e.dur, e.pitch, e.vel) for e in backing if e.part == BASS], swing=swing))
    mid.tracks.append(_track("Piano comping", 2, 0,
                             [(e.start, e.dur, e.pitch, e.vel) for e in backing if e.part == COMP], swing=swing))
    mid.tracks.append(_track("Drums", 9, None,
                             [(e.start, e.dur, e.pitch, e.vel) for e in backing if e.part in (RIDE, HAT)], swing=swing))
    mid.save(path)
