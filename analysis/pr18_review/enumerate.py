"""Exact P(>=5) for all 10,090,080 ballots on the PR's own 100k selection sample."""
import sys, json, time, itertools
import numpy as np
sys.path.insert(0, ".")
from engine.montecarlo import run_mc
from engine.optimizer import optimize, p_ge5, build_outcome_matrices, Ballot
from engine.teams import load_stage
from scripts.singapore_stage1 import FIXTURE, SEED, SPREAD, market_inputs

teams, _ = load_stage(FIXTURE); data = json.loads(FIXTURE.read_text())
ids = [t.id for t in teams]; names = {t.id: t.name for t in teams}; pos = {i: k for k, i in enumerate(ids)}
ratings, prices = market_inputs(teams, data["openers"], 0.5)
sel = run_mc(teams, ratings, SPREAD, 100_000, seed=SEED, market_blend=prices)
out = optimize(sel, teams); hc = out.recommended
n = len(sel.sample)
A30 = np.zeros((n, 16), np.int8); AAD = np.zeros((n, 16), np.int8); A03 = np.zeros((n, 16), np.int8)
for k, rec in enumerate(sel.sample):
    for i in ids:
        w, l = rec[i]
        if w == 3 and l == 0: A30[k, pos[i]] = 1
        elif w == 3: AAD[k, pos[i]] = 1
        elif w == 0 and l == 3: A03[k, pos[i]] = 1
sets6 = np.array(list(itertools.combinations(range(12), 6)))            # 924 advance sets over the 12 free slots
setmask = np.zeros(924, np.int64)
for j, s in enumerate(sets6): setmask[j] = sum(1 << int(b) for b in s)
pc = np.array([bin(x).count("1") for x in range(4096)])
overlap = pc[np.arange(4096)[:, None] & setmask[None, :]]                 # 4096 x 924
K = np.stack([(overlap >= t).astype(np.float32) for t in range(1, 6)])    # t = 5 - base hits, base in 0..4
pow2 = (1 << np.arange(12)).astype(np.int64)
t0 = time.time(); best = (-1, None); top = []; total = 0
pairs = list(itertools.combinations(range(16), 2))
for p30 in pairs:
    rest14 = [x for x in range(16) if x not in p30]
    b30 = A30[:, p30[0]] + A30[:, p30[1]]
    for p03 in itertools.combinations(rest14, 2):
        free = [x for x in rest14 if x not in p03]
        base = b30 + A03[:, p03[0]] + A03[:, p03[1]]                      # 0..4
        pat = AAD[:, free].astype(np.int64) @ pow2
        H = np.bincount(base.astype(np.int64) * 4096 + pat, minlength=5 * 4096).reshape(5, 4096).astype(np.float32)
        cnt = np.zeros(924, np.float32)
        for b in range(5): cnt += H[b] @ K[4 - b]                         # threshold t = 5-b -> K index t-1
        total += 924
        j = int(np.argmax(cnt)); c = float(cnt[j])
        top.append((c, p30, p03, tuple(free[x] for x in sets6[j])))
        if c > best[0]: best = (c, (p30, p03, tuple(free[x] for x in sets6[j])))
print(f"enumerated {total:,} ballots on n={n:,} sims in {time.time()-t0:.0f}s")
def show(p30, adv, p03): return " | ".join(",".join(names[ids[x]] for x in g) for g in (p30, adv, p03))
c, (p30, p03, adv) = best
gb = Ballot(tuple(ids[x] for x in p30), tuple(ids[x] for x in adv), tuple(ids[x] for x in p03))
M = build_outcome_matrices(sel.sample, ids)
print(f"global optimum: P>=5 {c/n:.5f} (optimizer's own scorer on it: {p_ge5(gb, M):.5f}) :: {show(p30, adv, p03)}")
print(f"hill-climb card: P>=5 {out.recommended_pge5:.5f} :: " + " | ".join(",".join(names[i] for i in g) for g in (hc.picks_30, hc.picks_adv, hc.picks_03)))
print(f"in-sample gap: {(c/n - out.recommended_pge5)*100:.3f} pp; same card: {set(gb.picks_30)==set(hc.picks_30) and set(gb.picks_adv)==set(hc.picks_adv) and set(gb.picks_03)==set(hc.picks_03)}")
top.sort(reverse=True)
print("best ballot per (3-0 pair, 0-3 pair), top 6:")
for c2, a, b, d in top[:6]: print(f"  {c2/n:.5f} :: {show(a, d, b)}")
# chalk baselines on the same sample
by_seed = list(range(16))
chalk_seed = Ballot(tuple(ids[x] for x in by_seed[:2]), tuple(ids[x] for x in by_seed[2:8]), tuple(ids[x] for x in by_seed[14:]))
by_r = sorted(range(16), key=lambda x: -teams[x].rating)
chalk_vrs = Ballot(tuple(ids[x] for x in by_r[:2]), tuple(ids[x] for x in by_r[2:8]), tuple(ids[x] for x in by_r[14:]))
print(f"chalk by seed: {p_ge5(chalk_seed, M):.5f}; chalk by Valve points: {p_ge5(chalk_vrs, M):.5f}; marginal-greedy (ballot A): {out.pge5_a:.5f}")
json.dump({"chalk_seed": [chalk_seed.picks_30, chalk_seed.picks_adv, chalk_seed.picks_03], "chalk_vrs": [chalk_vrs.picks_30, chalk_vrs.picks_adv, chalk_vrs.picks_03],
           "ballot_a": [out.ballot_a.picks_30, out.ballot_a.picks_adv, out.ballot_a.picks_03]}, open(sys.argv[1], "w"))
