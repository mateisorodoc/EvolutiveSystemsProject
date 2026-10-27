"""Turn a melody into sound: a soft electric-piano tone with the chords underneath."""

import numpy as np

import melody as mel

SAMPLE_RATE = 44100           # samples per second
TEMPO = 140                   # beats per minute
BEAT = 60 / TEMPO             # seconds per beat
SWING = 2 / 3                 # jazz "swing": the first eighth of each beat lasts 2/3 of the beat


def tone(midi, seconds, volume):
    """A simple tone: a sine wave plus one overtone, fading out."""
    freq = 440 * 2 ** ((midi - 69) / 12)                 # MIDI 69 = A4 = 440 Hz
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE  # time of every sample, in seconds
    wave = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)

    decay = np.exp(-3 * t)                         # the note slowly gets quieter...
    release = np.minimum(1, (seconds - t) * 50)    # ...and fades to 0 in its last 20 ms (avoids a click)
    return volume * wave * decay * release


def render(melody):
    """Build the whole audio clip as one numpy array."""
    length = len(melody) / 2 * BEAT + 1.0          # 2 notes per beat, plus 1 s for the last note to ring
    audio = np.zeros(int(length * SAMPLE_RATE))

    def add(start_seconds, sound):
        """Mix `sound` into `audio`, starting at `start_seconds` (cut off if it runs past the end)."""
        start = int(start_seconds * SAMPLE_RATE)
        end = min(len(audio), start + len(sound))
        audio[start:end] += sound[: end - start]

    # chords: one per bar (4 beats), low and quiet
    for bar, chord in enumerate(mel.CHORDS):
        for pitch_class in chord.tones:
            add(bar * 4 * BEAT, tone(48 + pitch_class, 4 * BEAT, 0.12))

    # melody: swung eighth notes (long-short, long-short, ...)
    for i, midi in enumerate(melody):
        beat = i // 2
        if i % 2 == 0:                       # first eighth of the beat: long
            start = beat * BEAT
            duration = SWING * BEAT
        else:                                # second eighth: short
            start = beat * BEAT + SWING * BEAT
            duration = (1 - SWING) * BEAT
        add(start, tone(midi, duration * 1.3, 0.35))   # * 1.3: let each note ring a little (legato)

    return audio / np.max(np.abs(audio)) * 0.8         # normalise the volume


def play(melody):
    """Play a melody. Returns an error message, or None if it worked."""
    try:
        import sounddevice
        sounddevice.play(render(melody).astype(np.float32), SAMPLE_RATE)
        return None
    except Exception as error:      # no sound card, PortAudio missing, ...
        return str(error)
