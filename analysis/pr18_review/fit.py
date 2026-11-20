import os, sys, json, math, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stages import SPEC, load

ALL_BO3 = {("Cologne 2026", 3)}  # one round per day in Valve's dates; every other stage plays two rounds on day 1
rows = []  # event, stage, round, diff (winner-oriented a=first alphabetical), y, bo3
for spec in SPEC:
    ms, comp, st = load(spec)
    assert len(comp) == 16 and len(ms) == 33, spec
    rec = {t: [0, 0] for t in comp}
    # round = each team's nth match; within a day lower Match ID = later, so sort date asc, id desc
    for m in ms:
        a, b = sorted((m["winner"], m["loser"]))
        rnd = sum(rec[a]) + 1; assert rnd == sum(rec[b]) + 1, (spec, m)
        bo3 = (spec[0], spec[1]) in ALL_BO3 or 2 in rec[a] or 2 in rec[b]
        rows.append(dict(event=spec[0], stage=spec[1], round=rnd, a=a, b=b, ra=st[a][1], rb=st[b][1],
                         y=int(m["winner"] == a), bo3=bo3, date=m["date"], id=m["id"]))
        rec[m["winner"]][0] += 1; rec[m["loser"]][1] += 1
    fin = collections.Counter(tuple(v) for v in rec.values())
    assert fin == {(3,0):2,(3,1):3,(3,2):3,(2,3):3,(1,3):3,(0,3):2}, (spec, fin)
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "major_swiss_matches.json"), "w"), indent=1)
ev = np.array([r["event"] for r in rows]); stg = np.array([f'{r["event"]} S{r["stage"]}' for r in rows])
d = np.array([r["ra"] - r["rb"] for r in rows], float); y = np.array([r["y"] for r in rows]); bo3 = np.array([r["bo3"] for r in rows])
print(f"n={len(rows)} series; Bo3 {bo3.sum()}, Bo1 {(~bo3).sum()}; favorite (higher Valve points) won {np.mean((d>0)==(y==1)):.3f}; mean |diff| {np.abs(d).mean():.0f} pts")

def p_series(d, S, bo3):
    p = 1 / (1 + 10 ** (-d / S)); return np.where(bo3, p * p * (3 - 2 * p), p)
def ll(S, idx=slice(None)):  # mean log loss
    p = p_series(d[idx], S, bo3[idx]); yy = y[idx]
    return -np.mean(yy * np.log(p) + (1 - yy) * np.log(1 - p))
GRID = np.arange(150, 3001, 10.0)
def mle(idx=slice(None)):
    return GRID[int(np.argmin([ll(S, idx) for S in GRID]))]

S_hat = mle()
print(f"\nMLE spread (map-level, Bo3 closed form): {S_hat:.0f}   log loss at MLE {ll(S_hat):.4f}")
for S in (300, 400, 411, 500, 600, 700, 800, 1000): print(f"  S={S:>4}: log loss {ll(S):.4f}")
print(f"  coin flip: {math.log(2):.4f}")
# likelihood-ratio interval: 2*n*(ll(S)-ll(S_hat)) < 2.71 (90%), 3.84 (95%)
n = len(rows); lr = np.array([2 * n * (ll(S) - ll(S_hat)) for S in GRID])
for lvl, c in ((90, 2.706), (95, 3.841)):
    ok = GRID[lr < c]; print(f"  profile-likelihood {lvl}% interval: {ok.min():.0f} to {ok.max():.0f}" + (" (hits grid edge)" if ok.max() >= GRID[-1] else ""))
print(f"  LR test of S=600 vs MLE: chi2={2*n*(ll(600)-ll(S_hat)):.2f}; S=400: {2*n*(ll(400)-ll(S_hat)):.2f}")

rng = np.random.default_rng(0)
def boot(labels, B=4000):
    u = np.unique(labels); out = []
    for _ in range(B):
        idx = np.concatenate([np.flatnonzero(labels == k) for k in rng.choice(u, len(u))]); out.append(mle(idx))
    return np.array(out)
bs = boot(stg); np.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "boot_spread.npy"), bs)
print(f"\nstage-cluster bootstrap (9 stages, B=4000): median {np.median(bs):.0f}; 90% {np.percentile(bs,5):.0f} to {np.percentile(bs,95):.0f}; 95% {np.percentile(bs,2.5):.0f} to {np.percentile(bs,97.5):.0f}; share >= grid max {np.mean(bs>=GRID[-1]):.3f}")
bm = boot(np.arange(len(rows)), 2000)
print(f"match-level bootstrap: 90% {np.percentile(bm,5):.0f} to {np.percentile(bm,95):.0f}")
print("\nper-event / per-stage MLE:")
for e in np.unique(ev): print(f"  {e}: n={np.sum(ev==e)} MLE {mle(ev==e):.0f}  ll@600 {ll(600, ev==e):.4f} ll@400 {ll(400, ev==e):.4f}")
s1 = np.array([r["stage"] == 1 for r in rows]); print(f"  Stage 1 only (3 stages): n={s1.sum()} MLE {mle(s1):.0f} ll@600 {ll(600,s1):.4f} ll@400 {ll(400,s1):.4f} ll@MLE {ll(mle(s1),s1):.4f}")
for k in (1,2,3):
    m_ = np.array([r["stage"] == k for r in rows]); print(f"  stage {k}: MLE {mle(m_):.0f}, favorite acc {np.mean((d[m_]>0)==(y[m_]==1)):.3f}")
b1 = ~bo3; print(f"  Bo1 only: n={b1.sum()} MLE {mle(b1):.0f};  Bo3 only: n={bo3.sum()} MLE {mle(bo3):.0f}")

print("\nwalk-forward (fit on earlier events, score the next):")
tot = {"wf": 0, 600: 0, 400: 0, "n": 0}
for train, test in ((["Austin 2025"], "Budapest 2025"), (["Austin 2025", "Budapest 2025"], "Cologne 2026")):
    tr = np.isin(ev, train); te = ev == test; Sw = mle(tr)
    print(f"  train {train} -> S={Sw:.0f}; test {test}: ll@fit {ll(Sw,te):.4f}  ll@600 {ll(600,te):.4f}  ll@400 {ll(400,te):.4f}  coin {math.log(2):.4f}")
    for k, v in (("wf", ll(Sw, te)), (600, ll(600, te)), (400, ll(400, te))): tot[k] += v * te.sum()
    tot["n"] += te.sum()
print(f"  pooled out-of-sample (n={tot['n']}): walk-forward {tot['wf']/tot['n']:.4f}, S=600 {tot[600]/tot['n']:.4f}, S=400 {tot[400]/tot['n']:.4f}")
# paired SE of per-match loss difference 600 vs coin on all data
def losses(S):
    p = p_series(d, S, bo3); return -(y * np.log(p) + (1 - y) * np.log(1 - p))
for S in (600, S_hat):
    df = math.log(2) - losses(S); print(f"  gain over coin at S={S:.0f}: {df.mean():.4f} +/- {df.std(ddof=1)/math.sqrt(n):.4f} per series")
# reliability at S=600
p6 = p_series(np.abs(d), 600, bo3); win = ((d > 0) == (y == 1)).astype(float)
print("\nreliability at S=600 (favorite's predicted vs actual win rate):")
for lo, hi in ((.5,.55),(.55,.6),(.6,.7),(.7,1.0)):
    m_ = (p6 >= lo) & (p6 < hi); print(f"  pred {lo:.2f}-{hi:.2f}: n={m_.sum():>3} mean pred {p6[m_].mean():.3f} actual {win[m_].mean():.3f}")
