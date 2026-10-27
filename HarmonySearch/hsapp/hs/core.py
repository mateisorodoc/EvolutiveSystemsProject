"""Harmony Search engine.

Implements three variants on one generic engine:

* ``classic`` - Geem, Kim & Loganathan (2001), "A New Heuristic Optimization
  Algorithm: Harmony Search". Fixed HMCR, PAR and bandwidth (bw).
* ``ihs``     - Mahdavi, Fesanghary & Damangir (2007), "An improved harmony
  search algorithm for solving optimization problems". PAR grows linearly
  and bw shrinks exponentially with the improvisation number.
* ``ghs``     - Omran & Mahdavi (2008), "Global-best harmony search". Pitch
  adjustment is replaced by copying a value from the best harmony in memory.

The engine works one improvisation at a time (``step``) and records *why*
every value of the new harmony was chosen, so the UI can explain each step
(memory consideration, pitch adjustment, random selection, global best).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

VARIANTS = ("classic", "ihs", "ghs")

# Where a value of a new harmony came from (one code per decision variable).
SRC_RANDOM = 0     # random selection           (probability 1 - HMCR)
SRC_MEMORY = 1     # memory consideration       (probability HMCR * (1 - PAR))
SRC_ADJUSTED = 2   # memory + pitch adjustment  (probability HMCR * PAR)
SRC_BEST = 3       # GHS: copied from the best harmony (replaces pitch adjustment)


@dataclass
class Variable:
    """One decision variable (one "instrument" of the orchestra).

    ``lo``/``hi`` are inclusive bounds. Discrete variables take integer values.
    ``sample`` and ``adjust`` may override the default random selection and
    pitch adjustment, e.g. so that a "rest" token in a melody is never
    pitch-adjusted into a note.
    """

    name: str
    lo: float
    hi: float
    discrete: bool = False
    sample: Optional[Callable[[np.random.Generator], float]] = None
    adjust: Optional[Callable[[float, float, np.random.Generator], float]] = None

    @property
    def span(self) -> float:
        return float(self.hi - self.lo)

    def random(self, rng: np.random.Generator) -> float:
        if self.sample is not None:
            return float(self.sample(rng))
        if self.discrete:
            return float(rng.integers(int(self.lo), int(self.hi) + 1))
        return float(rng.uniform(self.lo, self.hi))

    def pitch_adjust(self, value: float, bw_frac: float, rng: np.random.Generator) -> float:
        """Move ``value`` to a neighbour. ``bw_frac`` is the bandwidth as a fraction of the range."""
        if self.adjust is not None:
            return float(self.adjust(value, bw_frac, rng))
        if self.discrete:
            steps = max(1, int(round(bw_frac * self.span)))
            delta = int(rng.integers(1, steps + 1)) * (1 if rng.random() < 0.5 else -1)
            return float(np.clip(value + delta, self.lo, self.hi))
        delta = bw_frac * self.span * rng.uniform(-1.0, 1.0)
        return float(np.clip(value + delta, self.lo, self.hi))


@dataclass
class HSParams:
    variant: str = "classic"
    hms: int = 10            # Harmony Memory Size
    hmcr: float = 0.9        # Harmony Memory Considering Rate
    par: float = 0.3         # Pitch Adjusting Rate (classic)
    bw: float = 0.05         # bandwidth, fraction of each variable's range (classic)
    par_min: float = 0.1     # IHS / GHS
    par_max: float = 0.9     # IHS / GHS
    bw_min: float = 0.001    # IHS
    bw_max: float = 0.2      # IHS
    ni: int = 5000           # Number of Improvisations (stopping criterion)
    seed: Optional[int] = None

    def par_at(self, t: int) -> float:
        if self.variant == "classic":
            return self.par
        return self.par_min + (self.par_max - self.par_min) * min(t, self.ni) / max(1, self.ni)

    def bw_at(self, t: int) -> float:
        if self.variant == "ihs":
            c = np.log(max(self.bw_min, 1e-12) / max(self.bw_max, 1e-12)) / max(1, self.ni)
            return float(self.bw_max * np.exp(c * min(t, self.ni)))
        return self.bw


@dataclass
class Improvisation:
    """Everything that happened during one improvisation (for teaching mode)."""

    t: int                       # improvisation number (1-based)
    harmony: np.ndarray          # the new harmony
    fitness: float               # its objective value
    accepted: bool               # did it enter the memory?
    replaced_row: int            # memory row that was replaced (-1 if rejected)
    worst_before: float          # fitness of the worst harmony before the update
    par: float                   # PAR used
    bw: float                    # bw used
    source: np.ndarray           # SRC_* code per variable
    r1: np.ndarray               # random number compared with HMCR
    r2: np.ndarray               # random number compared with PAR (nan if not drawn)
    row: np.ndarray              # memory row the value was taken from (-1 if random)
    before_adjust: np.ndarray    # value before pitch adjustment (nan if not adjusted)


class HarmonySearch:
    """Generic Harmony Search optimiser.

    ``objective(x) -> float`` is minimised, or maximised when ``maximize`` is True.
    """

    def __init__(
        self,
        variables: List[Variable],
        objective: Callable[[np.ndarray], float],
        params: HSParams,
        maximize: bool = False,
    ):
        if params.variant not in VARIANTS:
            raise ValueError(f"unknown variant {params.variant!r}")
        self.variables = list(variables)
        self.objective = objective
        self.params = params
        self.maximize = maximize
        self.rng = np.random.default_rng(params.seed)
        self.n = len(self.variables)
        # GHS copies x_best[k] with a random k; that only makes sense when all
        # variables share the same domain. Otherwise we use x_best[i].
        self._same_domain = all(
            v.lo == self.variables[0].lo and v.hi == self.variables[0].hi and v.discrete == self.variables[0].discrete
            for v in self.variables
        )
        self.t = 0
        self.evaluations = 0
        self.memory = np.zeros((0, self.n))
        self.fitness = np.zeros(0)
        self.history_best: List[float] = []
        self.history_mean: List[float] = []
        self.history_worst: List[float] = []
        self.last: Optional[Improvisation] = None
        self.initialize()

    # ----------------------------------------------------------------- helpers
    def _score(self, f):
        """Higher is always better internally."""
        return f if self.maximize else -f

    @property
    def best_index(self) -> int:
        return int(np.argmax(self._score(self.fitness)))

    @property
    def worst_index(self) -> int:
        return int(np.argmin(self._score(self.fitness)))

    @property
    def best(self) -> np.ndarray:
        return self.memory[self.best_index].copy()

    @property
    def best_fitness(self) -> float:
        return float(self.fitness[self.best_index])

    @property
    def finished(self) -> bool:
        return self.t >= self.params.ni

    def _record(self):
        self.history_best.append(float(self.fitness[self.best_index]))
        self.history_mean.append(float(np.mean(self.fitness)))
        self.history_worst.append(float(self.fitness[self.worst_index]))

    def _evaluate(self, x: np.ndarray) -> float:
        self.evaluations += 1
        return float(self.objective(x))

    # --------------------------------------------------------------- algorithm
    def initialize(self):
        """Step 2 of HS: fill the harmony memory with HMS random harmonies."""
        hms = max(1, int(self.params.hms))
        self.memory = np.array([[v.random(self.rng) for v in self.variables] for _ in range(hms)], dtype=float)
        self.fitness = np.array([self._evaluate(x) for x in self.memory])
        self.t = 0
        self.last = None
        self.history_best, self.history_mean, self.history_worst = [], [], []
        self._record()

    def reevaluate(self):
        """Re-score the memory after the objective changed (e.g. new weights)."""
        self.fitness = np.array([self._evaluate(x) for x in self.memory])
        if self.history_best:
            self.history_best[-1] = float(self.fitness[self.best_index])
            self.history_mean[-1] = float(np.mean(self.fitness))
            self.history_worst[-1] = float(self.fitness[self.worst_index])

    def step(self) -> Improvisation:
        """Steps 3-4 of HS: improvise one new harmony and update the memory."""
        p = self.params
        rng = self.rng
        self.t += 1
        par = p.par_at(self.t)
        bw = p.bw_at(self.t)
        hms = len(self.memory)
        best_row = self.best_index

        x = np.empty(self.n)
        source = np.empty(self.n, dtype=np.int8)
        r1 = rng.random(self.n)
        r2 = np.full(self.n, np.nan)
        rows = np.full(self.n, -1, dtype=int)
        before = np.full(self.n, np.nan)

        for i, var in enumerate(self.variables):
            if r1[i] < p.hmcr:
                # memory consideration: take the value of variable i from a random harmony
                k = int(rng.integers(hms))
                rows[i] = k
                x[i] = self.memory[k, i]
                source[i] = SRC_MEMORY
                r2[i] = rng.random()
                if r2[i] < par:
                    if p.variant == "ghs":
                        j = int(rng.integers(self.n)) if self._same_domain else i
                        before[i] = x[i]
                        x[i] = self.memory[best_row, j]
                        source[i] = SRC_BEST
                    else:
                        before[i] = x[i]
                        x[i] = var.pitch_adjust(x[i], bw, rng)
                        source[i] = SRC_ADJUSTED
            else:
                x[i] = var.random(rng)
                source[i] = SRC_RANDOM

        f = self._evaluate(x)
        worst = self.worst_index
        worst_f = float(self.fitness[worst])
        accepted = self._score(f) > self._score(worst_f)
        if accepted:
            self.memory[worst] = x
            self.fitness[worst] = f
        self._record()
        self.last = Improvisation(
            t=self.t,
            harmony=x,
            fitness=f,
            accepted=bool(accepted),
            replaced_row=worst if accepted else -1,
            worst_before=worst_f,
            par=par,
            bw=bw,
            source=source,
            r1=r1,
            r2=r2,
            row=rows,
            before_adjust=before,
        )
        return self.last


def run_to_completion(variables, objective, params: HSParams, maximize=False, progress=None, cancelled=None):
    """Run a full search and return the best-so-far curve (used to compare variants)."""
    hs = HarmonySearch(variables, objective, params, maximize=maximize)
    while not hs.finished:
        hs.step()
        if progress is not None and hs.t % 50 == 0:
            progress(hs.t)
        if cancelled is not None and cancelled():
            break
    return np.array(hs.history_best), hs
