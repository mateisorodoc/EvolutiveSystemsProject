"""Tab 3: a short, presentation-friendly explanation of Harmony Search (EN / RO)."""

from PySide6.QtWidgets import QHBoxLayout, QTextBrowser, QVBoxLayout, QWidget

from . import theme
from .i18n import I18N

def css():
    return f"""
<style>
body {{ color: {theme.TEXT}; font-size: 15px; line-height: 155%; }}
h1 {{ color: {theme.TEXT}; font-size: 26px; font-weight: 600; margin-bottom: 4px; }}
h2 {{ color: {theme.TEXT}; font-size: 19px; font-weight: 600; margin-top: 28px; margin-bottom: 6px; }}
p, li {{ color: {theme.TEXT}; }}
.muted {{ color: {theme.MUTED}; }}
pre {{ background: {theme.PANEL}; color: {theme.TEXT}; padding: 14px; font-family: Consolas, Menlo, monospace; font-size: 13px; }}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid {theme.BORDER}; padding: 6px 10px; }}
th {{ background: {theme.PANEL}; color: {theme.MUTED}; text-align: left; }}
.m {{ color: {theme.SOURCE_COLORS[1]}; font-weight: bold; }}
.a {{ color: {theme.SOURCE_COLORS[2]}; font-weight: bold; }}
.r {{ color: {theme.SOURCE_COLORS[0]}; font-weight: bold; }}
.b {{ color: {theme.SOURCE_COLORS[3]}; font-weight: bold; }}
</style>
"""

EN = """
<h1>Harmony Search, explained</h1>
<p class="muted">Geem, Kim &amp; Loganathan (2001). A metaheuristic inspired by jazz musicians improvising together.</p>

<h2>The metaphor</h2>
<table>
<tr><th>Jazz band</th><th>Optimisation</th></tr>
<tr><td>a musician</td><td>a decision variable</td></tr>
<tr><td>the notes a musician can play</td><td>the variable's range</td></tr>
<tr><td>a harmony (everybody plays one note)</td><td>a candidate solution vector</td></tr>
<tr><td>the band's memory of good harmonies</td><td>the Harmony Memory (HM)</td></tr>
<tr><td>audience's aesthetic judgement</td><td>the objective (fitness) function</td></tr>
<tr><td>practice, improvisation after improvisation</td><td>iterations</td></tr>
</table>
<p>When improvising, every musician either <span class="m">plays a note they remember</span> (memory consideration),
<span class="a">plays a remembered note slightly adjusted</span> (pitch adjustment), or
<span class="r">plays something completely new</span> (random selection).</p>

<h2>Parameters</h2>
<ul>
<li><b>HMS</b> (Harmony Memory Size): how many harmonies the band remembers.</li>
<li><b>HMCR</b> (Harmony Memory Considering Rate): probability to take a value from memory (otherwise random). High HMCR = exploitation.</li>
<li><b>PAR</b> (Pitch Adjusting Rate): probability that a value taken from memory is then nudged to a neighbour.</li>
<li><b>bw</b> (bandwidth): how far a pitch adjustment can move (here: a fraction of each variable's range).</li>
<li><b>NI</b> (Number of Improvisations): the stopping criterion.</li>
</ul>
<p>For each variable: P(<span class="m">memory</span>) = HMCR·(1−PAR), P(<span class="a">adjusted</span>) = HMCR·PAR, P(<span class="r">random</span>) = 1−HMCR.</p>

<h2>The algorithm</h2>
<pre>
1. Define f(x), the variables x_i and their ranges; choose HMS, HMCR, PAR, bw, NI.
2. Fill the Harmony Memory with HMS random vectors and evaluate them.
3. Improvise a new harmony x':
     for each variable i:
         if rand() &lt; HMCR:                      # memory consideration
             x'_i = HM[random row][i]
             if rand() &lt; PAR:                   # pitch adjustment
                 x'_i = x'_i ± rand() · bw
         else:                                   # random selection
             x'_i = random value in the range of x_i
4. If x' is better than the worst harmony in HM, replace the worst one.
5. Repeat 3–4 until NI improvisations are done. Return the best harmony.
</pre>
<p>Unlike a genetic algorithm, HS builds the new vector from <i>all</i> memory members (not from two parents),
and it keeps a steady-state memory: one candidate per iteration, replacing only the worst.</p>

<h2>Variants compared in the app</h2>
<ul>
<li><b>Classic HS (2001)</b>: fixed PAR and bw.</li>
<li><b>Improved HS, IHS (Mahdavi et al., 2007)</b>: PAR grows and bw shrinks with the iteration number t:<br>
PAR(t) = PAR<sub>min</sub> + (PAR<sub>max</sub> − PAR<sub>min</sub>)·t/NI &nbsp;&nbsp;
bw(t) = bw<sub>max</sub>·exp(ln(bw<sub>min</sub>/bw<sub>max</sub>)·t/NI).<br>
Early: big jumps (exploration). Late: fine tuning (exploitation).</li>
<li><b>Global-best HS, GHS (Omran &amp; Mahdavi, 2008)</b>: instead of a pitch adjustment, the value is
<span class="b">copied from the best harmony</span> (inspired by particle swarm optimisation). No bw needed.
When the variables have different domains (the synth), the same variable of the best harmony is used.</li>
</ul>
<p>Use <b>Compare variants</b> to run all three with identical seeds and plot the average best-so-far curves.</p>

<h2>Jazz composer</h2>
<p><b>Encoding:</b> one decision variable per swung eighth note. Its value is a pitch inside the chosen range,
<b>—</b> (hold the previous note) or <b>·</b> (rest). Pitch adjustment moves a note up/down by a few semitones —
literally what a musician does. Holds and rests are never pitch-adjusted.</p>
<p><b>Fitness</b> (maximised, 0–100): weighted average of nine music-theory criteria, chord tones on the beat,
notes inside the chord scale (or chromatic approach notes), smooth voice leading, melodic contour, rhythmic density,
syncopation, phrasing (breathing), motif repetition, and resolution at the end. Every weight is a dial;
changing one re-scores the whole memory live.</p>
<p>The rhythm section (walking bass, comping, ride cymbal) is generated by rules and is not evolved.</p>

<h2>Sound matcher</h2>
<p><b>Encoding:</b> one decision variable per synth knob, as the knob position in [0, 1]
(waveforms, detune, mix, noise, filter cutoff/resonance/envelope, ADSR, gate, vibrato). Optionally the pitch is
locked to the detected pitch (YIN algorithm), this removes the hardest, most multimodal dimension.</p>
<p><b>Fitness</b> (minimised): weighted mean absolute difference, in dB, between the target and the synth:
mel spectrogram (timbre over time), loudness envelope, and average spectrum (overall brightness).</p>
<p><b>Known-target demo:</b> "Random target" generates a sound from a hidden random patch. Because the true knob
values are known, you can show how close Harmony Search gets to them.</p>

<h2>Demo tips</h2>
<ul>
<li>Set <b>Speed</b> to 1–5 improvisations/s and open <i>Memory &amp; step</i>: every value of every new harmony is
explained (r₁ vs HMCR, r₂ vs PAR, which memory row it came from).</li>
<li>In the Jazz tab choose <i>Show: Last improvisation</i>, notes are coloured by where HS took them from.</li>
<li>Try HMCR = 0 (pure random search) vs 0.95, or PAR = 0 (no fine tuning) to show why each ingredient matters.</li>
<li>Click any row of the Harmony Memory to see/hear that harmony.</li>
</ul>
"""

RO = """
<h1>Harmony Search, pe înțelesul tuturor</h1>
<p class="muted">Geem, Kim &amp; Loganathan (2001). O metaeuristică inspirată de muzicienii de jazz care improvizează împreună.</p>

<h2>Metafora</h2>
<table>
<tr><th>Formație de jazz</th><th>Optimizare</th></tr>
<tr><td>un muzician</td><td>o variabilă de decizie</td></tr>
<tr><td>notele pe care le poate cânta</td><td>domeniul variabilei</td></tr>
<tr><td>o armonie (fiecare cântă o notă)</td><td>un vector soluție candidat</td></tr>
<tr><td>memoria formației cu armoniile bune</td><td>Memoria Armoniilor (HM)</td></tr>
<tr><td>judecata estetică a publicului</td><td>funcția obiectiv (fitness)</td></tr>
<tr><td>repetiții, improvizație după improvizație</td><td>iterații</td></tr>
</table>
<p>La fiecare improvizație, fiecare muzician fie <span class="m">cântă o notă pe care și-o amintește</span> (consultarea memoriei),
fie <span class="a">cântă o notă amintită, ușor ajustată</span> (ajustarea tonului), fie
<span class="r">cântă ceva complet nou</span> (selecție aleatoare).</p>

<h2>Parametri</h2>
<ul>
<li><b>HMS</b> (dimensiunea memoriei): câte armonii reține formația.</li>
<li><b>HMCR</b> (rata de consultare a memoriei): probabilitatea de a lua o valoare din memorie (altfel aleator). HMCR mare = exploatare.</li>
<li><b>PAR</b> (rata de ajustare a tonului): probabilitatea ca o valoare luată din memorie să fie mutată la o valoare vecină.</li>
<li><b>bw</b> (lățimea de bandă): cât de mult poate muta o ajustare (aici: fracție din domeniul fiecărei variabile).</li>
<li><b>NI</b> (numărul de improvizații): criteriul de oprire.</li>
</ul>
<p>Pentru fiecare variabilă: P(<span class="m">memorie</span>) = HMCR·(1−PAR), P(<span class="a">ajustat</span>) = HMCR·PAR, P(<span class="r">aleator</span>) = 1−HMCR.</p>

<h2>Algoritmul</h2>
<pre>
1. Se definesc f(x), variabilele x_i și domeniile lor; se aleg HMS, HMCR, PAR, bw, NI.
2. Se umple Memoria Armoniilor cu HMS vectori aleatori și se evaluează.
3. Se improvizează o armonie nouă x':
     pentru fiecare variabilă i:
         dacă rand() &lt; HMCR:                    # consultarea memoriei
             x'_i = HM[rând aleator][i]
             dacă rand() &lt; PAR:                 # ajustarea tonului
                 x'_i = x'_i ± rand() · bw
         altfel:                                 # selecție aleatoare
             x'_i = valoare aleatoare din domeniul lui x_i
4. Dacă x' este mai bună decât cea mai slabă armonie din HM, o înlocuiește.
5. Se repetă 3–4 până la NI improvizații. Se returnează cea mai bună armonie.
</pre>
<p>Spre deosebire de un algoritm genetic, HS construiește vectorul nou din <i>toți</i> membrii memoriei (nu din doi părinți)
și folosește o memorie „steady-state”: un singur candidat pe iterație, care înlocuiește doar cea mai slabă soluție.</p>

<h2>Variantele comparate în aplicație</h2>
<ul>
<li><b>HS clasic (2001)</b>: PAR și bw fixe.</li>
<li><b>HS îmbunătățit, IHS (Mahdavi et al., 2007)</b>: PAR crește și bw scade cu numărul iterației t:<br>
PAR(t) = PAR<sub>min</sub> + (PAR<sub>max</sub> − PAR<sub>min</sub>)·t/NI &nbsp;&nbsp;
bw(t) = bw<sub>max</sub>·exp(ln(bw<sub>min</sub>/bw<sub>max</sub>)·t/NI).<br>
La început: salturi mari (explorare). La final: reglaj fin (exploatare).</li>
<li><b>HS cu cel mai bun global, GHS (Omran &amp; Mahdavi, 2008)</b>: în locul ajustării tonului, valoarea este
<span class="b">copiată din cea mai bună armonie</span> (inspirat de optimizarea cu roiuri de particule). Nu are nevoie de bw.
Când variabilele au domenii diferite (sintetizatorul), se folosește aceeași variabilă din cea mai bună armonie.</li>
</ul>
<p>Folosiți <b>Compară variantele</b> pentru a rula toate trei cu aceleași seed-uri și a vedea curbele medii.</p>

<h2>Compozitorul de jazz</h2>
<p><b>Codificare:</b> o variabilă de decizie pentru fiecare optime „swing”. Valoarea ei este o înălțime din intervalul ales,
<b>—</b> (ține nota anterioară) sau <b>·</b> (pauză). Ajustarea tonului mută o notă cu câteva semitonuri în sus/jos —
exact ce face un muzician. Notele ținute și pauzele nu sunt ajustate.</p>
<p><b>Fitness</b> (maximizat, 0–100): media ponderată a nouă criterii de teorie muzicală, note din acord pe timpi,
note din scara acordului (sau note cromatice de apropiere), mers melodic lin, contur melodic, densitate ritmică,
sincope, frazare (respirație), repetarea motivului și rezolvarea finală. Fiecare pondere are un buton rotativ;
modificarea ei re-evaluează live întreaga memorie.</p>
<p>Secția ritmică (walking bass, acompaniament, cinel ride) este generată prin reguli și nu este evoluată.</p>

<h2>Potrivirea sunetului</h2>
<p><b>Codificare:</b> o variabilă de decizie pentru fiecare buton al sintetizatorului, ca poziție în [0, 1]
(forme de undă, detune, mix, zgomot, filtru cutoff/rezonanță/anvelopă, ADSR, durată, vibrato). Opțional, înălțimea este
blocată la cea detectată (algoritmul YIN), astfel dispare dimensiunea cea mai grea și mai multimodală.</p>
<p><b>Fitness</b> (minimizat): diferența absolută medie ponderată, în dB, între țintă și sintetizator:
spectrograma mel (timbrul în timp), anvelopa de volum și spectrul mediu (strălucirea).</p>
<p><b>Demo cu țintă cunoscută:</b> „Țintă aleatoare” generează un sunet dintr-un patch ascuns. Pentru că valorile reale
ale butoanelor sunt cunoscute, puteți arăta cât de aproape ajunge Harmony Search de ele.</p>

<h2>Sfaturi pentru prezentare</h2>
<ul>
<li>Setați <b>Viteza</b> la 1–5 improvizații/s și deschideți <i>Memorie și pas</i>: fiecare valoare a fiecărei armonii noi
este explicată (r₁ vs HMCR, r₂ vs PAR, din ce rând al memoriei provine).</li>
<li>În tab-ul Jazz alegeți <i>Arată: Ultima improvizație</i>, notele sunt colorate după proveniența lor.</li>
<li>Încercați HMCR = 0 (căutare pur aleatoare) vs 0.95, sau PAR = 0 (fără reglaj fin) pentru a arăta rolul fiecărui ingredient.</li>
<li>Click pe orice rând din Memoria Armoniilor pentru a vedea/asculta acea armonie.</li>
</ul>
"""


class LearnTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        self.setMaximumWidth(16777215)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        # a comfortable reading measure (~70 characters per line), centred on wide screens
        self.browser.setMaximumWidth(780)
        self.browser.setFrameShape(QTextBrowser.NoFrame)
        self.browser.document().setDocumentMargin(28)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.browser, 100)
        row.addStretch(1)
        lay.addLayout(row)
        I18N.changed.connect(self._update)
        theme.THEME.changed.connect(self._update)
        self._update()

    def _update(self):
        self.browser.setHtml(css() + (RO if I18N.lang == "ro" else EN))
