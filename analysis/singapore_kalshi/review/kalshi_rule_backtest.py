"""Apply the PR's Kalshi entry rule to the 98 Cologne 2026 Swiss matches, using Polymarket closing prices as the tradable price."""
import json, math, sys
import numpy as np
sys.path.insert(0, ".")
from analysis.singapore_kalshi import model
from engine.probs import series_best_of
J = json.load(open(sys.argv[1]))
fd = model.fit(); lo_s, hi_s = fd["spread90"]; R = fd["residual80"]; print("fit:", fd["fitted"], fd["spread90"], round(R, 3))
def fc(d, bo, S, s90, resid):
    p = series_best_of(1 / (1 + 10 ** (-d / S)), bo); gaps = [math.log(10) * d / s for s in s90]
    return p, series_best_of(1 / (1 + math.exp(-(min(gaps) - resid))), bo), series_best_of(1 / (1 + math.exp(-(max(gaps) + resid))), bo)
def run(label, S, s90, resid, rule):
    n = pnl = wins = 0; fav = 0; rows = []
    for j in J:
        bo = 3 if j["bo3"] else 1
        p, low, high = fc(j["ra"] - j["rb"], bo, S, s90, resid)
        for side, (pm, fair, lowp, won) in {"a": (j["pm"], p, low, j["y"]), "b": (1 - j["pm"], 1 - p, 1 - high, 1 - j["y"])}.items():
            price = min(0.99, pm + 0.005); cost = price + 0.07 * price * (1 - price)
            take = (lowp > cost) if rule == "stressed" else (fair > cost + 0.02)
            if take:
                n += 1; pnl += won - cost; wins += won; fav += pm > 0.5; rows.append((cost, won, fair, pm))
    if n:
        c = np.array([r[0] for r in rows]); w = np.array([r[1] for r in rows]); per = w - c
        print(f"{label}: entries {n} of {2*len(J)} sides; bought at mean {c.mean():.3f}; won {int(wins)}/{n} ({wins/n:.3f}); market favorites among entries {fav}; P&L per contract {per.mean():+.4f} +/- {per.std(ddof=1)/math.sqrt(n):.4f}; total {per.sum():+.2f} contracts-dollars; model fair avg {np.mean([r[2] for r in rows]):.3f}")
    else: print(f"{label}: no entries")
run("PR rule, published parameters (1410; 980-2040; 0.564)", fd["fitted"], fd["spread90"], R, "stressed")
run("PR rule, walk-forward spread for Cologne (1660)", fd["walk"]["Cologne 2026"]["spread"], fd["spread90"], R, "stressed")
run("no stress: model fair > cost + 2c, spread 1410", fd["fitted"], fd["spread90"], R, "naive")
run("no stress, spread 1660", 1660, fd["spread90"], R, "naive")
# how the model's fair value compares with the market on the same matches
pm = np.array([j["pm"] for j in J]); y = np.array([j["y"] for j in J])
pmod = np.array([fc(j["ra"] - j["rb"], 3 if j["bo3"] else 1, 1660, fd["spread90"], R)[0] for j in J])
ll = lambda p: float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
print(f"log loss on these 98: market close {ll(np.clip(pm,.005,.995)):.4f}, model at walk-forward 1660 {ll(pmod):.4f}, 50/50 blend {ll((pm+pmod)/2):.4f}")
# does the model add information beyond the market? logistic regression of outcome on market logit + model logit
import numpy.linalg as la
X = np.column_stack([np.log(pm / (1 - pm)), np.log(pmod / (1 - pmod))]); b = np.zeros(2)
for _ in range(100):
    q = 1 / (1 + np.exp(-X @ b)); g = X.T @ (y - q); Hm = (X * (q * (1 - q))[:, None]).T @ X; b += la.solve(Hm, g)
se = np.sqrt(np.diag(la.inv(Hm))); print(f"outcome ~ market logit + model logit: market coef {b[0]:.2f} +/- {se[0]:.2f}, model coef {b[1]:.2f} +/- {se[1]:.2f}")
# Singapore: which sides would trigger at current Polymarket asks
print("Singapore openers at the frozen Polymarket asks vs published ceilings:")
ceil = {"9z": 39, "Lynn Vision": 23, "HEROIC": 38, "Imperial": 27, "100 Thieves": 41, "Chinggis Warriors": 21, "NIP": 35, "M80": 30, "Liquid": 39, "GOSH": 23, "PVISION": 37, "DENDELE": 26, "Eternal Fire": 38, "FlyQuest": 25, "FaZe": 37, "Wildcard": 27}
for o in json.load(open("data/singapore2026/stage1.json"))["openers"]:
    a, b = o["teams"]; aa, ab = round(o["ask"] * 100), round((1 - o["bid"]) * 100)
    for t, ask in ((a, aa), (b, ab)):
        if ask <= ceil[t]: print(f"  WOULD TAKE {t} at {ask}c (ceiling {ceil[t]}c)")
