# Harmony Search: a jazz melody (simple version)

A small teaching app. Harmony Search (Geem, Kim & Loganathan, 2001) composes a 4-bar jazz line:
32 swung eighth notes over **Dm7 | G7 | Cmaj7 | Cmaj7**, a ii–V–I in C.

Turn the dials, press **Step** to watch one improvisation explained note by note, or **Run** to
let the band practise. Press **Play best melody** to hear the result with the chords underneath.

## Run it

```bash
pip install -r requirements.txt
python main.py
```

It works on Windows and macOS (Python 3.10+).

## The code

| File | What it does | You need to know |
|---|---|---|
| `harmony_search.py` | The algorithm. Generic: it knows nothing about music. | classes, lists, `random` |
| `melody.py` | The problem: chords, note names and the fitness function. | `%`, sets, `namedtuple` |
| `sound.py` | Turns a melody into audio with numpy and plays it. | numpy arrays, sine waves |
| `main.py` | The window: dials, buttons, plots and the step-by-step explanation. | Qt signals and timers, matplotlib |

Read them in that order. A few design choices make the code easier to follow:

- **`LabeledDial`** (in `main.py`): a `QDial` holds only whole numbers, so each dial has a `step`
  (HMCR uses 0.01, so position 90 means 0.90). The rest of the program only calls `dial.value()`
  and gets real values.
- **Every log entry has the same keys** (`how`, `r1`, `row`, `r2`, `before`, `value`), and a key is
  `None` when that step didn't happen. For example, a random note has no memory row.
- **`step()` records the HMCR and PAR it used**, so the explanation stays correct even if you turn
  a dial afterwards.
- **`main.py` is split into sections**: building the window (`build_...` methods), running the
  search, and showing the results.
- **The Run button uses a `QTimer`**: Qt programs don't loop by themselves. The timer calls
  `run_tick()` 10 times per second, and in between Qt redraws the window and handles clicks.

## How Harmony Search works

| Jazz band | Optimisation |
|---|---|
| a musician | a variable (here: one of the 32 notes) |
| the notes they can play | the variable's range (C4 to G5) |
| a harmony | a solution (here: a whole melody) |
| the band's memory | the Harmony Memory (HMS melodies) |
| the audience | the fitness function |

1. Fill the memory with HMS random melodies.
2. Improvise a new melody. For each note:
   - with probability **HMCR**, copy that note from a random melody in memory, and then,
     with probability **PAR**, move it up or down by 1 to **bw** semitones;
   - otherwise, pick a completely random note.
3. If the new melody is better than the worst one in memory, it replaces it.
4. Repeat until **NI** improvisations have been made.

## What makes a good melody (the fitness)

Three criteria, each scored from 0 to 1, combined as a weighted average using the three weight dials:

- **Chord tones**: notes on the beat belong to the chord playing at that moment.
- **Smoothness**: steps (1–2 semitones) score best, big leaps score nothing, repeated notes score a little.
- **Ending on C**: the last note is C, the home note.

Changing a weight re-scores the whole memory immediately, so you can watch the ranking change.

## Things to try

- Set **HMCR = 0**: every note is random, and the search barely improves.
- Set **PAR = 0**: notes are only copied, never fine-tuned, so progress stalls early.
- Set the **Smoothness** weight to 10 and the others to 0, then listen.
- Set **Speed** to its minimum and use **Step** to read every decision.

## What was left out (compared with the full app)

This version was simplified on purpose, following the "distill" guidance of
[Impeccable](https://impeccable.style/): one purpose, one obvious action, nothing extra.

| Removed | Why |
|---|---|
| Sound matcher (synth + recording) | One feature only. It needed FFT and spectrum code that's hard to follow. |
| IHS and GHS variants, variant comparison | Classic HS is enough to learn the idea. |
| Rests and held notes | Continuous eighth notes are a real bebop style, and the algorithm stays fully generic. |
| Six of nine fitness criteria | Three criteria are enough to hear the difference. |
| Choice of progression, key and range | Fixed to a ii–V–I in C. |
| Walking bass, drums, MIDI/WAV export | Playback with the chords is enough to judge a melody. |
| Romanian translation, light/dark themes, custom widgets and styles | Plain Qt widgets (`QDial`, `QPushButton`, `QGroupBox`) are easier to understand. |
