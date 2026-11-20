import json, math, sys
import numpy as np
sys.path.insert(0, ".")
import scripts.singapore_stage1 as sg
from engine.montecarlo import run_mc
from engine.optimizer import Ballot, build_outcome_matrices, correct_counts
from engine.teams import load_stage
teams, _ = load_stage(sg.FIXTURE); data = json.loads(sg.FIXTURE.read_text()); pub = json.loads(sg.FORECAST.read_text())
ids = [t.id for t in teams]; byname = {t.name: t.id for t in teams}
base = [tuple(byname[n] for n in pub["card"][k]) for k in ("3-0", "3-1 or 3-2", "0-3")]
def card(sixth): return Ballot(base[0], tuple(byname[sixth] if i == byname["DENDELE"] else i for i in base[1]), base[2])
cards = {n: card(n) for n in ("DENDELE", "M80", "9z")}
grid = [400, 500, 600, 700, 800, 1000, 1200, 1400, 1700, 2000, 2500, 3000]
w = np.array([0.010, 0.041, 0.069, 0.081, 0.117, 0.141, 0.111, 0.105, 0.094, 0.089, 0.080, 0.063]); w /= w.sum()
out = {n: [] for n in cards}
for S_pts in grid:
    sg.SPREAD = S_pts / 10; r, p = sg.market_inputs(teams, data["openers"], 1.0)
    e = run_mc(teams, r, S_pts / 10, 80000, seed=411, market_blend=p); M = build_outcome_matrices(e.sample, ids); del e
    for n, c in cards.items(): out[n].append(float(np.mean(correct_counts(c, M) >= 5)))
    del M
print("spread   " + "  ".join(f"{n:>8}" for n in cards))
for k, S_pts in enumerate(grid): print(f"{S_pts:>6}   " + "  ".join(f"{out[n][k]:.4f}  " for n in cards))
print("weighted " + "  ".join(f"{float(w @ np.array(out[n])):.4f}  " for n in cards))
