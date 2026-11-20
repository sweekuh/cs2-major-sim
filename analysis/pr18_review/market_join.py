import json, math, numpy as np
AL = {"Aurora Gaming":"Aurora","BetBoom Team":"BetBoom","FUT Esports":"FUT","Heroic":"HEROIC","Sinners":"SINNERS","Team Falcons":"Falcons","TheMongolz":"The MongolZ"}
mk = json.load(open("dl/cologne_market.json")); rows = [r for r in json.load(open("major_swiss_matches.json")) if r["event"] == "Cologne 2026"]
idx = {}
for o in mk:
    a, b = (AL.get(x, x) for x in o["outcomes"]); st = int(o["title"].split("Stage ")[-1][0])
    idx[(st, frozenset((a, b)))] = (a, o)
J = []
for r in rows:
    k = (r["stage"], frozenset((r["a"], r["b"])))
    if k not in idx: print("no market", r["stage"], r["a"], r["b"]); continue
    first, o = idx[k]
    if o["close"] is None: print("no close", o["slug"]); continue
    pm = o["close"] if first == r["a"] else 1 - o["close"]          # market P(a wins series)
    res_a = float(o["result"][0]) if first == r["a"] else float(o["result"][1])
    assert res_a == r["y"], (o["slug"], res_a, r["y"])               # Polymarket resolution agrees with Valve W/L
    fmt_bo3 = "(BO3)" in o["title"]; assert fmt_bo3 == r["bo3"], (o["title"], r["bo3"], r["round"])
    J.append(dict(r, pm=pm, vol=o["vol"], lag=o["close_lag"]))
n = len(J); print(f"joined {n} of {len(rows)}; results agree with Polymarket resolutions on all; Bo1/Bo3 replay agrees with market titles on all")
y = np.array([j["y"] for j in J]); d = np.array([j["ra"] - j["rb"] for j in J], float); bo3 = np.array([j["bo3"] for j in J]); pm = np.clip(np.array([j["pm"] for j in J]), .005, .995)
def lossv(p): return -(y*np.log(p) + (1-y)*np.log(1-p))
def pv(S): p = 1/(1+10**(-d/S)); return np.where(bo3, p*p*(3-2*p), p)
print(f"median volume ${np.median([j['vol'] for j in J]):,.0f}; closing price taken a median {np.median([-j['lag'] for j in J]):.0f}s before start")
lm = lossv(pm); print(f"log loss: market close {lm.mean():.4f} | Valve pts S=600 {lossv(pv(600)).mean():.4f} | S=1000 {lossv(pv(1000)).mean():.4f} | coin {math.log(2):.4f}")
for S in (600, 1000): df = lossv(pv(S)) - lm; print(f"  S={S} minus market: {df.mean():+.4f} +/- {df.std(ddof=1)/math.sqrt(n):.4f}")
print(f"  market favorite won {np.mean((pm>.5)==(y==1)):.3f}; Valve-points favorite won {np.mean((d>0)==(y==1)):.3f}")
# market-implied spread: invert series price to map prob, regress log10 odds on Valve point diff through the origin
def inv_bo3(q):
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo+hi)/2
        if mid*mid*(3-2*mid) < q: lo = mid
        else: hi = mid
    return (lo+hi)/2
pmap = np.array([inv_bo3(q) if b else q for q, b in zip(pm, bo3)]); z = np.log10(pmap/(1-pmap))
def implied(mask, label):
    slope = (d[mask] @ z[mask]) / (d[mask] @ d[mask]); r = np.corrcoef(d[mask], z[mask])[0, 1]
    rng = np.random.default_rng(1); ii = np.flatnonzero(mask); bs = []
    for _ in range(4000):
        k = rng.choice(ii, len(ii)); bs.append((d[k] @ d[k]) / (d[k] @ z[k]))
    print(f"  {label}: n={mask.sum()} market-implied spread {1/slope:.0f} pts/decade (90% {np.percentile(bs,5):.0f} to {np.percentile(bs,95):.0f}); corr(points diff, market log-odds) {r:.2f}; residual sd {np.std(z[mask]-slope*d[mask])/slope if False else np.std(z[mask]-slope*d[mask])*(1/slope):.0f} pts")
print("market-implied spread on Valve points (map level):")
st = np.array([j["stage"] for j in J]); rd = np.array([j["round"] for j in J])
implied(np.ones(n, bool), "all Cologne Swiss"); implied(st == 1, "Stage 1"); implied((st == 1) & (rd == 1), "Stage 1 round 1"); implied(rd == 1, "all round 1 (ratings freshest)"); implied(rd >= 3, "rounds 3-5")
# outcome MLE on the same matches when the market price is the predictor: calibration slope of market
from math import log
g = np.arange(0.4, 2.01, 0.02); zz = np.log(pm/(1-pm))
L = [np.mean(lossv(1/(1+np.exp(-b*zz)))) for b in g]; print(f"market calibration slope (1 = calibrated): {g[int(np.argmin(L))]:.2f}")
json.dump(J, open("cologne_joined.json", "w"))
