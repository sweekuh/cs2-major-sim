"""Joint spread x carry check on the PR's own evidence (historical-stages.json), using its own market_inputs."""
import json, math, sys
import numpy as np
sys.path.insert(0, ".")
import scripts.singapore_stage1 as sg
from engine.teams import Team
from engine.probs import series_prob
from odds.base import devig_fixed_two_way
H = json.load(open("data/singapore2026/evidence/historical-stages.json"))
def winner_probs(stage, S_pts, carry):
    """per-match P(actual winner); carry None = ratings only."""
    teams = [Team(t["seed"], t["name"], t["seed"], t["vrs"] / 10) for t in stage["teams"]]; by = {t.name: t for t in teams}
    ops = []
    for q in stage["openers"]:
        a, b = sorted(q["teams"], key=lambda n: by[n].seed); p = q["p"] if a == q["teams"][0] else 1 - q["p"]
        ops.append(dict(teams=[a, b], bid=p, ask=p))
    ratings = {t.id: t.rating for t in teams} if carry is None else sg.market_inputs(teams, ops, carry, S_pts / 10)[0]
    out = []
    for m in stage["matches"]:
        if m["round"] == 1: continue
        a, b = sorted([by[n] for n in m["teams"]], key=lambda t: t.seed)
        p = series_prob(ra=ratings[a.id], rb=ratings[b.id], bo3=m["bo"] == 3, S=S_pts / 10)
        out.append(p if a.name == m["winner"] else 1 - p)
    return np.array(out)
ev = list(H)
def pooled(S_pts, carry): return np.concatenate([winner_probs(H[e], S_pts, carry) for e in ev])
print("later-round log loss, 75 matches pooled (coin flip 0.6931); rows = spread, cols = ratings only / carry 0.5 / carry 1")
grid = [400, 500, 600, 700, 800, 1000, 1200, 1400, 1700, 2000, 3000]
T = {}
for S_pts in grid:
    row = [(-np.log(pooled(S_pts, c)).mean()) for c in (None, 0.5, 1.0)]; T[S_pts] = row
    print(f"  {S_pts:>5}: " + "  ".join(f"{x:.4f}" for x in row))
fine = np.arange(300, 4001, 25)
for lab, c in (("ratings only", None), ("half carry", 0.5), ("full carry", 1.0)):
    L = np.array([-np.log(pooled(s, c)).sum() for s in fine]); best = fine[int(np.argmin(L))]
    ok = fine[2 * (L - L.min()) < 2.706]
    print(f"{lab}: best spread {best} (log loss {L.min()/75:.4f}); 90% profile interval {ok.min()} to {ok.max()}{' (grid edge)' if ok.max()==fine[-1] else ''}; chi2 of 600 vs best: {2*(-np.log(pooled(600,c)).sum()-L.min()):.2f}")
print("per event, full carry: best spread and loss at 600 vs best")
for e in ev:
    L = np.array([-np.log(winner_probs(H[e], s, 1.0)).mean() for s in fine]); print(f"  {e}: best {fine[int(np.argmin(L))]}, loss {L.min():.4f} vs at 600 {-np.log(winner_probs(H[e],600,1.0)).mean():.4f}")
print("paired differences at 600 (positive = first is worse), mean +/- SE over 75 matches")
l = {c: -np.log(pooled(600, c)) for c in (None, 0.5, 1.0)}
for a, b, lab in ((None, 1.0, "ratings only minus full carry"), (0.5, 1.0, "half minus full carry")):
    d = l[a] - l[b]; print(f"  {lab}: {d.mean():+.4f} +/- {d.std(ddof=1)/math.sqrt(75):.4f}")
d = -np.log(pooled(600, 1.0)) + np.log(pooled(1400, 1.0)); print(f"  full carry at 600 minus full carry at 1400: {d.mean():+.4f} +/- {d.std(ddof=1)/math.sqrt(75):.4f}")
# leave-one-event-out choice of (spread, carry)
print("leave-one-event-out: choose (spread, carry) on two events, score the third")
tot = 0; tot600 = 0
for held in ev:
    tr = [e for e in ev if e != held]; best = None
    for s in fine[::2]:
        for c in (None, 0.5, 1.0):
            v = sum(-np.log(winner_probs(H[e], s, c)).sum() for e in tr)
            if best is None or v < best[0]: best = (v, s, c)
    a = -np.log(winner_probs(H[held], best[1], best[2])).mean(); b = -np.log(winner_probs(H[held], 600, 1.0)).mean(); tot += a; tot600 += b
    print(f"  hold out {held}: chose spread {best[1]}, carry {best[2]} -> {a:.4f}; PR setting (600, full) -> {b:.4f}")
print(f"  mean: chosen {tot/3:.4f} vs PR setting {tot600/3:.4f}")
# Kalshi vs Polymarket for Cologne openers; opener favorite records
pm = {frozenset(o["outcomes"]): o for o in json.load(open(sys.argv[1]))}
AL = {"BetBoom": "BetBoom Team", "HEROIC": "Heroic", "SINNERS": "Sinners"}
print("Cologne openers: Kalshi 10:00 UTC mid (PR) vs Polymarket close (mine)")
for q in H["cologne"]["openers"]:
    k = frozenset(AL.get(n, n) for n in q["teams"]); o = pm.get(k)
    if o is None or o["close"] is None: print("  ", q["teams"], q["p"], "no Polymarket close"); continue
    pc = o["close"] if o["outcomes"][0] == AL.get(q["teams"][0], q["teams"][0]) else 1 - o["close"]
    print(f"   {q['teams'][0]:>12} v {q['teams'][1]:<18} {q['p']:.3f} vs {pc:.3f}")
for e in ev:
    won = sum((q["p"] > .5) == (next(m for m in H[e]["matches"] if m["round"] == 1 and set(m["teams"]) == set(q["teams"]))["winner"] == q["teams"][0]) for q in H[e]["openers"])
    print(f"  {e}: opener favorites won {won}/8; mean favorite price {np.mean([max(q['p'],1-q['p']) for q in H[e]['openers']]):.3f}")
