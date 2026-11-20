import json, math, sys
import numpy as np
sys.path.insert(0, ".")
import scripts.singapore_stage1 as sg
from engine.montecarlo import run_mc
from engine.optimizer import Ballot, ballot_a, ballot_b, build_outcome_matrices, marginals_from_matrices, correct_counts
from engine.teams import load_stage, Team
from engine.probs import series_prob
teams, _ = load_stage(sg.FIXTURE); data = json.loads(sg.FIXTURE.read_text()); pub = json.loads(sg.FORECAST.read_text())
ids = [t.id for t in teams]; names = {t.id: t.name for t in teams}; byname = {t.name: t.id for t in teams}
CARD = Ballot(*[tuple(byname[n] for n in pub["card"][k]) for k in ("3-0", "3-1 or 3-2", "0-3")])
show = lambda c: " | ".join(",".join(names[i] for i in g) for g in (c.picks_30, c.picks_adv, c.picks_03))
# reproduce headline
sg.SPREAD = 60.0; r, p = sg.market_inputs(teams, data["openers"], 1.0)
e = run_mc(teams, r, 60.0, 200_000, seed=sg.SEED + 1, market_blend=p); M = build_outcome_matrices(e.sample, ids)
print(f"reproduce: P>=5 {np.mean(correct_counts(CARD, M) >= 5):.6f} (published {pub['evaluation']['p_ge5']})"); del e, M
# likelihood weights for spread from the PR's own 75 later-round matches under full carry
H = json.load(open("data/singapore2026/evidence/historical-stages.json"))
def nll(S_pts):
    tot = 0.0
    for st in H.values():
        ts = [Team(t["seed"], t["name"], t["seed"], t["vrs"] / 10) for t in st["teams"]]; by = {t.name: t for t in ts}; ops = []
        for q in st["openers"]:
            a, b = sorted(q["teams"], key=lambda n: by[n].seed); pp = q["p"] if a == q["teams"][0] else 1 - q["p"]; ops.append(dict(teams=[a, b], bid=pp, ask=pp))
        sg.SPREAD = S_pts / 10; rr = sg.market_inputs(ts, ops, 1.0)[0]
        for m in st["matches"]:
            if m["round"] == 1: continue
            a, b = sorted([by[n] for n in m["teams"]], key=lambda t: t.seed)
            q = series_prob(ra=rr[a.id], rb=rr[b.id], bo3=m["bo"] == 3, S=S_pts / 10); tot -= math.log(q if a.name == m["winner"] else 1 - q)
    return tot
grid = [400, 500, 600, 700, 800, 1000, 1200, 1400, 1700, 2000, 2500, 3000]
L = np.array([nll(s) for s in grid]); w = np.exp(-(L - L.min()))
# flat prior in log-spread: weight each grid point by its log-width
lg = np.log(grid); width = np.gradient(lg); w = w * width; w /= w.sum()
print("== published card under full carry, by spread (60k select, 60k fresh eval)")
res = {}
for S_pts in grid:
    sg.SPREAD = S_pts / 10; r, p = sg.market_inputs(teams, data["openers"], 1.0)
    sel = run_mc(teams, r, S_pts / 10, 60000, seed=301, market_blend=p); Ms = build_outcome_matrices(sel.sample, ids); del sel
    best = ballot_b(ballot_a(*marginals_from_matrices(Ms), ), Ms, ids); del Ms
    e = run_mc(teams, r, S_pts / 10, 60000, seed=302, market_blend=p); M = build_outcome_matrices(e.sample, ids); del e
    a = correct_counts(CARD, M) >= 5; b = correct_counts(best, M) >= 5; d = b.astype(float) - a.astype(float); res[S_pts] = a.mean()
    print(f"  S={S_pts:>4}: published {a.mean():.4f} | re-optimized {b.mean():.4f} (regret {d.mean():+.4f}+/-{d.std(ddof=1)/math.sqrt(len(d)):.4f}) | likelihood weight {w[grid.index(S_pts)]:.3f} | {show(best) if set(best.all_ids)!=set(CARD.all_ids) or best.picks_30!=CARD.picks_30 else 'same card'}")
    del M
vals = np.array([res[s] for s in grid]); order = np.argsort(vals); cw = np.cumsum(w[order])
q = lambda x: vals[order][np.searchsorted(cw, x)]
print(f"likelihood-weighted P>=5: mean {float(w @ vals):.4f}; 5% {q(.05):.4f}, 50% {q(.5):.4f}, 95% {q(.95):.4f}")
