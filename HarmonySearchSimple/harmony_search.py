"""Classic Harmony Search (Geem, Kim & Loganathan, 2001) for integer variables.

The idea: a band of musicians improvises together. Each musician (variable)
plays one note (value). Good harmonies are remembered in the Harmony Memory.

For every new improvisation, each musician either
  - plays a note from memory          (probability HMCR),
    and maybe shifts it a little      (probability PAR, by at most bw),
  - or plays a completely random note (probability 1 - HMCR).
If the new harmony is better than the worst one in memory, it replaces it.
"""

import random


class HarmonySearch:
    def __init__(self, n_vars, low, high, fitness, hms=10, hmcr=0.9, par=0.3, bw=1, seed=None):
        self.n_vars = n_vars      # number of variables (musicians)
        self.low = low            # smallest allowed value
        self.high = high          # largest allowed value
        self.fitness = fitness    # function: harmony -> score (higher is better)
        self.hms = hms            # Harmony Memory Size
        self.hmcr = hmcr          # Harmony Memory Considering Rate
        self.par = par            # Pitch Adjusting Rate
        self.bw = bw              # bandwidth: biggest pitch adjustment
        self.rng = random.Random(seed)

        # Step 1: fill the harmony memory with random harmonies
        self.memory = [self.random_harmony() for _ in range(hms)]
        self.scores = [fitness(h) for h in self.memory]
        self.iteration = 0
        self.history = [max(self.scores)]   # best score after every improvisation

    def random_harmony(self):
        return [self.rng.randint(self.low, self.high) for _ in range(self.n_vars)]

    def best(self):
        i = self.scores.index(max(self.scores))
        return self.memory[i], self.scores[i]

    def worst_index(self):
        return self.scores.index(min(self.scores))

    def rescore(self):
        """Call this after the fitness function changed (e.g. new weights)."""
        self.scores = [self.fitness(h) for h in self.memory]

    def improvise(self):
        """Step 2: build a new harmony, one variable at a time.

        Returns the new harmony and a log with one entry per variable.
        Every entry has the same keys; a key is None when that step did not happen.
        """
        new = []
        log = []
        for i in range(self.n_vars):
            r1 = self.rng.random()
            row = None       # memory row we copied from
            r2 = None        # random number compared with PAR
            before = None    # value before the pitch adjustment

            if r1 < self.hmcr:
                # memory consideration: copy variable i from a random harmony in memory
                how = "memory"
                row = self.rng.randrange(self.hms)
                value = self.memory[row][i]
                r2 = self.rng.random()
                if r2 < self.par:
                    # pitch adjustment: move to a nearby value
                    how = "adjusted"
                    before = value
                    step = self.rng.randint(1, self.bw) * self.rng.choice([-1, 1])
                    value = min(self.high, max(self.low, value + step))
            else:
                # random selection: any value in the range
                how = "random"
                value = self.rng.randint(self.low, self.high)

            new.append(value)
            log.append({"how": how, "r1": r1, "row": row, "r2": r2, "before": before, "value": value})
        return new, log

    def step(self):
        """One full iteration: improvise, evaluate, update the memory (step 3)."""
        new, log = self.improvise()
        score = self.fitness(new)
        worst = self.worst_index()
        worst_score = self.scores[worst]

        if score > worst_score:
            self.memory[worst] = new
            self.scores[worst] = score
            replaced = worst
        else:
            replaced = None

        self.iteration += 1
        self.history.append(max(self.scores))
        return {
            "harmony": new,
            "score": score,
            "log": log,
            "worst_score": worst_score,
            "replaced": replaced,      # index of the replaced harmony, or None
            "hmcr": self.hmcr,         # the settings used, so the explanation stays correct
            "par": self.par,           # even if a dial is turned afterwards
        }
