# Harmony Search Studio

A desktop app for teaching and experimenting with the **Harmony Search (HS)** metaheuristic
(Geem, Kim & Loganathan, 2001), applied to two musical problems:

1. **Jazz Composer**: HS improvises a jazz melody over a chord progression.
2. **Sound Matcher**: HS turns the knobs of a subtractive synthesizer until it sounds like a target
   (a file, a microphone recording up to 10 s, or a random hidden patch).

Every algorithm parameter and every fitness weight is a dial. The app explains each improvisation
step by step and compares Classic HS with two well-known variants (IHS, GHS). The UI can be switched
between **English and Romanian** at any time.

---

## 1. Install and run

Requires **Python 3.10+**. It works on Windows and macOS (including Apple Silicon M1/M2/M3).

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### macOS (M1 MacBook Air)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The first time you press **Record**, macOS asks for microphone access for the app that launched
Python (Terminal, iTerm, VS Code…). If you denied it by mistake, re-enable it in
*System Settings → Privacy & Security → Microphone*, then restart the terminal.

`python main.py --maximized` starts the window maximized, which is handy on a projector.
`python main.py --dark` starts in the dark theme; the **Light / Dark** toggle in the header switches live.
The layout needs at least about 1240×800 px; on short screens the Sound Matcher work area scrolls.

**Dependencies** (all ship native wheels for Windows and Apple Silicon): PySide6 (Qt UI),
pyqtgraph (plots), numpy, scipy, sounddevice (PortAudio playback/recording), soundfile (audio files),
mido (MIDI export).

---

## 2. Using the app

### Shared Harmony Search panel (right column, both tabs)

| Control | Meaning |
|---|---|
| Classic / IHS / GHS | Algorithm variant (see §3). Switching restarts the search. |
| HMS | Harmony Memory Size. Changing it restarts the search. |
| HMCR | Harmony Memory Considering Rate. |
| PAR, bw | Pitch Adjusting Rate and bandwidth (Classic). |
| PAR min/max, bw min/max | Dynamic schedules for IHS (PAR, bw) and GHS (PAR). |
| NI | Number of Improvisations (stopping criterion). |
| Random seed | Same seed and same settings give an identical run. 0 = random. |
| Reset / Step / Run | Re-initialise the memory, do one improvisation, run or pause. |
| Speed | Improvisations per second. 1–5/s is ideal for live explanation; MAX is as fast as possible. |
| Compare variants… | Runs Classic, IHS and GHS N times with the same seeds and plots mean ± std convergence. |

You can change HMCR, PAR, bw, NI and the fitness weights **while the search is running**.

Bottom tabs:
- **Convergence**: best, mean and worst fitness in memory per improvisation, plus PAR(t) and bw(t).
- **Memory & step**: the full Harmony Memory (★ best, ▼ worst, orange = row just replaced; click a
  row to view or hear it), next to a table explaining the last improvisation variable by variable:
  the random number r₁ vs HMCR, the memory row used, r₂ vs PAR, and the value before and after
  pitch adjustment.

### Jazz Composer

- Choose a progression (ii–V–I, minor ii–V–i, jazz blues, an Autumn Leaves-style A section,
  Rhythm changes A, a Dorian modal vamp), a key and the number of choruses.
- Melody range, P(rest) and P(hold) define the search space and the random-selection distribution.
- The nine fitness weights and the two style targets (notes per bar, syncopation) shape the music.
- **Show**: *Best harmony*, *Last improvisation* (notes coloured by HS origin, with a strip showing the
  origin of every variable), or *Selected memory row*.
- Play with Rhodes, vibes or sax, a walking bass, piano comping and a ride cymbal. Tempo and swing
  only affect playback.
- **Export MIDI** writes four tracks (melody, bass, piano, drums) with chord markers.
  **Export WAV** writes the rendered audio.

### Sound Matcher

- **Target**: *Load file…* (wav, flac, ogg, mp3, aiff), *Record* (microphone, up to 10 s), or
  *Random target* (a hidden random patch, so the result can be compared with the truth in the
  *Known target* table).
- **Lock pitch**: the synth pitch is fixed to the detected pitch (YIN algorithm), or to the true pitch
  for random targets. You can correct it with the Pitch dial. Unlocked, HS must also find the pitch.
- **Analyse**: only the first N seconds are compared. Shorter targets give a faster search.
- **Synth knobs**: while HS runs they show the selected harmony. When paused, you can turn them
  yourself (*Show → Manual*) and try to beat HS.
- **A/B** plays the target, then the synth. Export the synth sound as WAV or the patch as JSON.

### Learn tab

A presentation-ready explanation (EN/RO): the metaphor, the parameters, pseudocode, the variants,
and how both problems are encoded.

---

## 3. The algorithm (notes for the report)

### 3.1 Classic Harmony Search (Geem et al., 2001)

1. Define the objective f(x) and the decision variables x_i ∈ X_i. Choose HMS, HMCR, PAR, bw, NI.
2. **Initialise** the Harmony Memory HM with HMS random vectors and evaluate them.
3. **Improvise** a new harmony x′. For each variable i:
   - with probability **HMCR**: *memory consideration*, x′_i = HM[k][i] for a random row k;
     - then with probability **PAR**: *pitch adjustment*, x′_i ← x′_i ± U(0,1)·bw
       (for discrete variables: a neighbouring value, up to round(bw·|X_i|) steps away);
   - otherwise (probability 1 − HMCR): *random selection* from X_i.
4. **Update**: if x′ is better than the worst harmony in HM, it replaces it.
5. Repeat steps 3–4 until **NI** improvisations have been done.

For each variable, P(memory only) = HMCR·(1−PAR), P(adjusted) = HMCR·PAR and P(random) = 1−HMCR.
The app shows these numbers live.

In this implementation **bw is a fraction of each variable's range**, so one dial makes sense for
variables with very different units (Hz, seconds, semitones).

### 3.2 Improved Harmony Search: IHS (Mahdavi, Fesanghary & Damangir, 2007)

PAR(t) = PAR_min + (PAR_max − PAR_min) · t / NI

bw(t) = bw_max · exp( ln(bw_min / bw_max) · t / NI )

Large adjustments early (exploration), fine tuning late (exploitation).

### 3.3 Global-best Harmony Search: GHS (Omran & Mahdavi, 2008)

Pitch adjustment is replaced by copying from the best harmony: x′_i = x_best,k with a random k,
and PAR(t) grows as in IHS. No bw is needed. When the variables do not share a domain (the synth
knobs), using a random k would be meaningless, so the app uses k = i. The Learn tab says the same.

### 3.4 Implementation

`hsapp/hs/core.py` is a single generic engine (`HarmonySearch`) that works on any list of `Variable`s
(continuous or discrete, with optional custom sampling and pitch-adjustment functions). `step()`
performs exactly one improvisation and records, for every variable, the random numbers drawn, the
decision taken and the memory row used. The teaching views read this record.

---

## 4. Problem 1: jazz melody composition

**Encoding.** The melody is a grid of swung eighth notes, 8 per 4/4 bar, with one discrete variable
per eighth. For a pitch range [low, high] with P = high − low + 1:

| value | meaning |
|---|---|
| 0 … P−1 | start a note with MIDI pitch low + value |
| P | **hold**: keep sounding the previous note |
| P+1 | **rest** |

Pitch adjustment moves a pitch by ±1…round(bw·P) semitones, which is exactly a musician's "pitch
adjustment". Holds and rests are never adjusted. Random selection draws a rest with P(rest), a hold
with P(hold), and otherwise a uniform pitch. A 4-bar ii–V–I has 32 variables; two choruses of a
12-bar blues have 192.

**Fitness** (maximised, 0–1, shown ×100) is the weighted average of nine criteria, each in [0, 1]:

| Criterion | Score |
|---|---|
| Chord tones | Notes starting on a beat: chord tone 1, tension 0.6, scale tone 0.25, approach 0.2, outside 0 |
| In scale | Every note in the chord scale (Dorian for m7, Mixolydian for 7, half-whole for 7♭9, …), or a chromatic approach note resolving by a half step |
| Smoothness | Interval score: step 1.0, third 0.85, up to a fifth 0.5, up to an octave 0.2; leaps followed by a step back are rewarded |
| Contour | Direction-change rate near 0.4, and no monotone runs longer than 6 notes |
| Density | Notes per bar close to the target dial |
| Syncopation | Fraction of off-beat onsets close to the target dial |
| Phrasing | Phrases of 1–2.5 bars separated by rests; penalties for very long silences |
| Motif | Bars 1–2, 3–4, … share rhythm (Jaccard) and melodic direction |
| Resolution | Final note is the root or 3rd of the last chord and held; phrases end on chord tones |

Changing a weight re-evaluates the whole memory immediately. The ranking changes in front of the
audience.

**Rhythm section** (not evolved): a rule-based walking bass with chromatic approach notes, rootless
shell-voicing piano comping in Charleston-like rhythms, and a ride cymbal with hi-hat on 2 and 4.

---

## 5. Problem 2: synth sound matching

**Synth** (`hsapp/audio/synth.py`): two band-limited oscillators (sine → triangle → saw → square
morph, PolyBLEP anti-aliasing), detune, mix, noise, a 2-pole resonant low-pass filter with its own
envelope, an amplitude ADSR, gate time and vibrato. That gives **17 knobs**, or 16 when the pitch is
locked. The filter is applied per STFT frame, so the fitness function compares exactly the
spectrogram you hear.

**Encoding.** One continuous variable per knob: the knob position in [0, 1]. Each knob maps the
position to a physical value (logarithmic for cutoff and times). So "HS turns the knobs" is meant
literally.

**Fitness** (minimised) is a weighted mean of three differences in dB, each normalised by an 80 dB
floor. Both signals are compared at 22,050 Hz with the same STFT (1024 points, hop 256):

| Component | What it compares |
|---|---|
| Timbre | 64-band mel spectrograms frame by frame (timbre over time) |
| Envelope | Loudness per frame (attack, decay, release) |
| Spectrum | Average mel spectrum (overall brightness, independent of timing) |

**Pitch detection**: YIN (de Cheveigné & Kawahara, 2002).

**Speed**: about 8 ms per evaluation for a 2 s target and about 45 ms for 10 s (measured on the
development laptop). For long recordings, lower *Analyse*.

**Observations for the report**
- Locking the pitch removes the most multimodal dimension; unlocked, HS often gets stuck at octave
  or fifth errors.
- Different patches can sound almost identical (osc1 ↔ osc2 with mix flipped, or an octave detune).
  The problem has many equivalent optima, so the *Known target* table can show "wrong" knob values
  with a very low error.
- In our quick tests (2 s random target, 2000 improvisations, HMS 20) the error went from 0.108 to
  about 0.020–0.025 for Classic and IHS, and to about 0.042 for GHS. The true patch scores 0.001.

---

## 6. Suggested experiments for the presentation or report

1. **HMCR sweep**: 0 (pure random search), 0.7, 0.9, 0.99. Show convergence and final fitness.
2. **PAR = 0 vs 0.3**: without pitch adjustment, HS cannot fine-tune.
3. **HMS 1 vs 10 vs 50**: diversity vs speed.
4. **Classic vs IHS vs GHS** with *Compare variants…*, 5+ runs each, same seeds.
5. **Fitness design**: set every weight except *Chord tones* to 0 and listen, then add *Smoothness*,
   then *Phrasing*. Each criterion changes the music audibly.
6. **Known target**: start the search, then compare the true and found knob values.

---

## 7. Visual design

The interface follows the [Impeccable](https://impeccable.style/) design guidance for an *Operate*
surface (a tool people work in):

- **Palette:** neutral surfaces, with near-black "ink" for actions, selection and dial values.
  Red, amber and green appear only as states (poor criterion, worst/replaced/best row, rejected
  or accepted improvisation).
- **Signature move:** four colour-blind-safe *provenance* colours (Okabe–Ito) mark where every value
  of a harmony came from: memory, memory plus pitch adjustment, random, or global best (GHS). They
  are used in the step table, the piano-roll strip, the legend and the PAR/bw curves, and nowhere
  else.
- **Note roles** in the piano roll use one ink lightness ramp (chord tone, tension, scale tone),
  an outline for approach notes and red for outside notes, so they never compete with provenance.
- **Light theme by default:** it reads better in a lit classroom on a projector. The dark theme is
  composed separately, not inverted.
- **Type:** the platform UI font (Segoe UI Variable on Windows, SF Pro on macOS) on a 12/13/15/20/28 px
  scale, with tabular numerals for every changing number. The Learn tab keeps lines to about
  70 characters.
- **Icons:** authored SVG icons in one stroke weight (`hsapp/ui/icons.py`); no emoji or glyph icons.
- All tokens live in `hsapp/ui/theme.py`.

## 8. Project structure

```
main.py                     entry point
hsapp/hs/core.py            Harmony Search engine (Classic, IHS, GHS) + per-step trace
hsapp/music/theory.py       chord qualities, chord scales, progressions
hsapp/music/composer.py     melody encoding + 9-criterion fitness
hsapp/music/backing.py      walking bass, comping, drums (rules)
hsapp/music/render.py       built-in instruments + swing rendering
hsapp/music/midi.py         MIDI export
hsapp/audio/dsp.py          STFT/ISTFT, mel filterbank, YIN pitch
hsapp/audio/synth.py        subtractive synth (17 knobs)
hsapp/audio/matcher.py      sound-matching problem (variables + objective)
hsapp/audio/io.py           playback, microphone, file I/O
hsapp/ui/theme.py           design tokens, light/dark palettes, type scale, stylesheet
hsapp/ui/icons.py           authored SVG icon set
hsapp/ui/                   PySide6 interface (dials, tabs, HS panel, EN/RO strings)
```

## 9. References

- Z. W. Geem, J. H. Kim, G. V. Loganathan, "A New Heuristic Optimization Algorithm: Harmony Search",
  *Simulation* 76(2), 60–68, 2001.
- M. Mahdavi, M. Fesanghary, E. Damangir, "An improved harmony search algorithm for solving
  optimization problems", *Applied Mathematics and Computation* 188(2), 1567–1579, 2007.
- M. G. H. Omran, M. Mahdavi, "Global-best harmony search", *Applied Mathematics and Computation*
  198(2), 643–656, 2008.
- A. de Cheveigné, H. Kawahara, "YIN, a fundamental frequency estimator for speech and music",
  *JASA* 111(4), 1917–1930, 2002.
