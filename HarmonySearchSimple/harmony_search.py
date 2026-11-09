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

        # Definim variabilele problemei

        self.n_vars = n_vars      # number of variables (musicians) = cate note sunt in solution vector
        self.low = low            # nota cea mai jaosa permisa
        self.high = high          # nota cea mai inalta permisa
        self.fitness = fitness    # function: harmony -> score (higher is better) = ia un solution vector si returneaza o valoare intre 0 si 1

        # Definim hypermarametrii algoritmului

        self.hms = hms            # Harmony Memory Size = cate solutii (melodii) sunt tinute in memorie at any given time
        self.hmcr = hmcr          # Harmony Memory Considering Rate = probabilitatea sa fie aleasa o nota dintr-o melodie deja existenta in memorie
        self.par = par            # Pitch Adjusting Rate = echivalent cu mutatia - e probabilitatea ca o nota sa fie pitched up/down
        self.bw = bw              # bandwidth - distanta maxima de semitonuri cu care o nota se poate schimba
        self.rng = random.Random(seed)

        # Step 1: fill the harmony memory with random harmonies
        self.memory = [self.random_harmony() for _ in range(hms)] # umplem memoria cu niste melodii random (size [hms][n_vars])
        self.scores = [fitness(h) for h in self.memory] # calculam fitnessul initial pt fiecare melodie random
        self.iteration = 0
        self.history = [max(self.scores)]   # best score after every improvisation

    def random_harmony(self):
        # Functie basic de facut o melodie random in intervalul de note
        return [self.rng.randint(self.low, self.high) for _ in range(self.n_vars)]

    def best(self):
        # Returnam cea mai buna melodie si scorul ei
        i = self.scores.index(max(self.scores))
        return self.memory[i], self.scores[i]

    def worst_index(self):
        # Returnam scorul la cea mai proasta melodie
        return self.scores.index(min(self.scores))

    def rescore(self):
        """Call this after the fitness function changed (e.g. new weights)."""
        self.scores = [self.fitness(h) for h in self.memory]

    def improvise(self):
        """Step 2: build a new harmony, one variable at a time.

        Returns the new harmony and a log with one entry per variable.
        Every entry has the same keys; a key is None when that step did not happen.
        """
        new = [] # lista cu cele 32 de note
        log = [] # o lista de dictionare in care tinem cum (de ce) fiecare nota a fost aleasa
        for i in range(self.n_vars):
            # facem asta pt toate notele dintr-o melodie
            r1 = self.rng.random() # un numar random intre 0 si 1
            row = None       # memory row we copied from
            r2 = None        # random number compared with PAR
            before = None    # value before the pitch adjustment

            if r1 < self.hmcr: 
                # daca hmcr e 0.9, r1 are o probabilitate de 90% sa fie in intervalul [0-0.9), deci alegem din memorie
                # memory consideration: copy variable i from a random harmony in memory
                how = "memory"
                row = self.rng.randrange(self.hms) # alegem o melodie random
                value = self.memory[row][i] # alegem nota cantata la pozitia i in acea melodie
                r2 = self.rng.random()
                if r2 < self.par:
                    # la fel ca la primul if
                    # pitch adjustment: move to a nearby value
                    how = "adjusted"
                    before = value # tinem nota originala ca sa o afisam in ui
                    step = self.rng.randint(1, self.bw) * self.rng.choice([-1, 1]) # pitch up sau down random, cu maxim bw semitones
                    value = min(self.high, max(self.low, value + step)) # clipping la nota ca sa stea in intervalul ales
            else:
                # random selection: any value in the range
                how = "random"
                value = self.rng.randint(self.low, self.high)

            new.append(value)
            log.append({"how": how, "r1": r1, "row": row, "r2": r2, "before": before, "value": value})
        return new, log

    def step(self):
        """One full iteration: improvise, evaluate, update the memory (step 3)."""
        new, log = self.improvise() # improvizam
        score = self.fitness(new) # calculam fitnessul (functia de fitness se poate schimba din ui, nu e una fixa)
        worst = self.worst_index()
        worst_score = self.scores[worst]

        if score > worst_score:
            # am gasit o melodie mai buna
            self.memory[worst] = new
            self.scores[worst] = score
            replaced = worst # tinem minte care slot a fost replaced
        else:
            replaced = None

        self.iteration += 1
        self.history.append(max(self.scores)) # tinem minte scorurile cele mai bune ca sa putem afisa graficul evolutiei 

        #returnam un dictionar despre toata iteratia
        return {
            "harmony": new,
            "score": score,
            "log": log,
            "worst_score": worst_score,
            "replaced": replaced,      # index of the replaced harmony, or None
            "hmcr": self.hmcr,         # the settings used, so the explanation stays correct
            "par": self.par,           # even if a dial is turned afterwards
        }
