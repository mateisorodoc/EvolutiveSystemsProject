"""The problem: a 4-bar jazz line (32 eighth notes) over a ii-V-I in C major.

A melody is a list of 32 MIDI note numbers (60 = C4 ... 79 = G5).
Each note is one variable for Harmony Search.
"""

from collections import namedtuple

LOWEST = 60          # C4
HIGHEST = 79         # G5
NOTES_PER_BAR = 8    # eighth notes in a 4/4 bar
N_NOTES = 32         # 4 bars

# A chord has a name and a set of chord tones.
# Tones are pitch classes: 0 = C, 1 = C#, 2 = D, ... 11 = B  (a MIDI note's pitch class is note % 12)
Chord = namedtuple("Chord", ["name", "tones"])

CHORDS = [
    Chord("Dm7", {2, 5, 9, 0}),      # D F A C
    Chord("G7", {7, 11, 2, 5}),      # G B D F
    Chord("Cmaj7", {0, 4, 7, 11}),   # C E G B
    Chord("Cmaj7", {0, 4, 7, 11}),
]

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def note_name(midi):
    """60 -> 'C4', 61 -> 'C#4', ..."""
    # Converts a MIDI integer into its letter name + octave number
    # midi % 12 ne da pitch class, care se mapeaza la o litera din NAMES
    # midi // 12 - 1 ne da octava
    # exemplu: midi = 62 
    # 62 % 12 = 2 -> NAMES[2] = "D"
    # 62 // 12 - 1 = 5 - 1 = 4 
    # rezulta "D4"
    
    return NAMES[midi % 12] + str(midi // 12 - 1)


def chord_at(i):
    """The chord that sounds under note number i (8 notes per bar)."""
    # i e pozitia in melodie (0 - 31) si vrem sa vedem ce chord e
    # Notele de la 0 la 7 sunt CHORDS[0] -> Dm7
    # Notele de la 8 la 15 sunt CHORDS[1] -> G7
    # Notele de la 16 la 23 sunt CHORDS[2] -> Cmaj7
    # Notele de la 24 la 31 sunt CHORDS[3] -> Cmaj7

    return CHORDS[i // NOTES_PER_BAR]


def is_chord_tone(melody, i):
    # Returneaza True or False, in functie daca nota de pe pozitia i apartine chordului respectiv
    # melody[i] % 12 ia pitch class ul (fara octava)
    # chord_at(i).tones ia setul de pitch classes din chordul pentru acel bar
    # exemplu: i = 10 (bar 2 over G7 {7, 11, 2, 5} = G, B, D, F)
    # daca melody[10] = 71 (B4) -> 71 % 12 = 11 -> True (11 e in {7, 11, 2, 5})
    # o sa fie afisat cu albastru in UI pe piano roll si o sa fie rewarded de chord_tones() 
    return melody[i] % 12 in chord_at(i).tones


# ---------------------------------------------------------------- the three criteria (each 0..1)

def chord_tones(melody):
    """Notes on the beat (1st, 3rd, 5th... eighth) should belong to the chord."""
    # Returneaza un scor de la 0 la 1
    # Selectam indicii pari pentru ca in 4/4 astia pica pe beat
    on_beat = range(0, N_NOTES, 2)
    # numaram cate din notele care cad pe beat sunt bune (apartin chordului)
    hits = sum(1 for i in on_beat if is_chord_tone(melody, i))
    # normalizam ca sa ne dea ceva intre 0.0 si 1.0
    return hits / len(on_beat)


def smoothness(melody):
    """Small steps sound melodic; big leaps and repeated notes sound clumsy."""
    # functia asta vede daca sunt pasi prea mici sau prea mari intre note consecutive (numara cate semitonuri)
    total = 0
    for a, b in zip(melody, melody[1:]):   # every pair of neighbouring notes
        jump = abs(b - a)                  # distance in semitones
        if jump == 0:
            total += 0.3          # repeated note
        elif jump <= 2:
            total += 1.0          # a step
        elif jump <= 4:
            total += 0.6          # a small skip (a third)
        elif jump <= 7:
            total += 0.2          # a leap
        # bigger than a fifth: 0 points
    return total / (N_NOTES - 1)


def ending(melody):
    """A line sounds finished when it ends on C (the home note)."""
    last = melody[-1] % 12
    # pitch class 0 este chiar C
    if last == 0:
        return 1.0
    # daca macar se termina intr-o nota din chord, ii dam jumate de punct
    if last in chord_at(N_NOTES - 1).tones:
        return 0.5
    return 0.0


CRITERIA = {"Chord tones": chord_tones, "Smoothness": smoothness, "Ending on C": ending}


def fitness(melody, weights):
    """Weighted average of the criteria, from 0 (bad) to 1 (perfect)."""
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    total = 0
    for name, criterion in CRITERIA.items():
        total += weights[name] * criterion(melody)
    return total / total_weight
