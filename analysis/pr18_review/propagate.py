import os, sys, json, math, collections
import numpy as np
SP = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, SP); sys.path.insert(0, ".")
from engine.montecarlo import run_mc
from engine.optimizer import Ballot, optimize
from engine.teams import load_stage, Team
from engine.seeding import seed_next_stage, InvitedTeam
from engine.swiss import simulate_stage
import scripts.singapore_stage1 as sg
from valve_parse import standings, REPO

def hits(card, sample):
    out = np.zeros(len(sample), int)
    for k, rec in enumerate(sample):
        out[k] = (sum(rec[i] == (3, 0) for i in card.picks_30) + sum(rec[i][0] == 3 and rec[i][1] >= 1 for i in card.picks_adv)
                  + sum(rec[i] == (0, 3) for i in card.picks_03))
    return out

# ---------- Part A: Singapore ----------
teams, _ = load_stage(sg.FIXTURE); data = json.loads(sg.FIXTURE.read_text()); pub = json.loads(sg.FORECAST.read_text())
ids = [t.id for t in teams]; names = {t.id: t.name for t in teams}; byname = {t.name: t.id for t in teams}
CARD = Ballot(*[tuple(byname[n] for n in pub["card"][k]) for k in ("3-0", "3-1 or 3-2", "0-3")])
base = json.load(open(os.path.join(SP, "baselines.json"))); CHALK = Ballot(*base["chalk_seed"]); CHALKV = Ballot(*base["chalk_vrs"])
def model(S_pts, carry=0.5):
    old = sg.SPREAD; sg.SPREAD = S_pts / 10
    try: return market_inputs_safe(carry)
    finally: sg.SPREAD = old
def market_inputs_safe(carry): return sg.market_inputs(teams, data["openers"], carry)
def show(c): return " | ".join(",".join(names[i] for i in g) for g in (c.picks_30, c.picks_adv, c.picks_03))
print("== A1. Published card at fixed spreads (PR structure: market round 1, carry 0.5); 40k select + 40k fresh eval")
for S_pts in (600, 1000, 1170, 1410, 2000):
    r, p = model(S_pts)
    sel = run_mc(teams, r, S_pts / 10, 40000, seed=101, market_blend=p); best = optimize(sel, teams).recommended; del sel
    e = run_mc(teams, r, S_pts / 10, 40000, seed=102, market_blend=p)
    hp, hb, hc, hv = (hits(c, e.sample) for c in (CARD, best, CHALK, CHALKV)); del e
    dd = (hb >= 5).astype(float) - (hp >= 5).astype(float)
    print(f"  S={S_pts:>4}: published {np.mean(hp>=5):.4f} (E hits {hp.mean():.2f}) | re-optimized {np.mean(hb>=5):.4f}, regret {dd.mean():+.4f}+/-{dd.std(ddof=1)/math.sqrt(len(dd)):.4f} | chalk-seed {np.mean(hc>=5):.4f} chalk-points {np.mean(hv>=5):.4f}")
    print(f"          re-optimized card: {show(best)}")
bs = np.load(os.path.join(SP, "boot_spread.npy")); rng = np.random.default_rng(42)
print("== A2. Nested propagation: spread drawn from the stage-cluster bootstrap; optional per-team rating noise tau (Valve points)")
for tau in (0, 67, 134):
    per = []; allh = []
    for k in range(240):
        S_pts = float(rng.choice(bs)); r, p = model(S_pts)
        if tau: r = {i: r[i] + rng.normal(0, tau / 10) for i in ids}
        e = run_mc(teams, r, S_pts / 10, 2500, seed=5000 + k, market_blend=p); h = hits(CARD, e.sample); del e
        per.append(np.mean(h >= 5)); allh.append(h)
    per = np.array(per); allh = np.concatenate(allh)
    noise = math.sqrt(per.mean() * (1 - per.mean()) / 2500)
    print(f"  tau={tau:>3}: P>=5 mean {allh.mean()>=0 and np.mean(allh>=5):.4f}; across-draw 5-95% {np.percentile(per,5):.3f} to {np.percentile(per,95):.3f}; min-max {per.min():.3f}-{per.max():.3f}; (inner sampling sd {noise:.3f})")

# ---------- Part B: historical calibration of P(>=5), Valve-points-only pipeline ----------
print("== B. Backtest on 9 real stages: card optimized in-model, then scored on what actually happened")
rows = json.load(open(os.path.join(SP, "major_swiss_matches.json")))
SEEDF = {"Austin 2025": "invitation/2025/standings_global_2025_05_05.md", "Budapest 2025": "invitation/2025/standings_global_2025_11_03.md", "Cologne 2026": "invitation/2026/standings_global_2026_05_04.md"}
res = collections.defaultdict(list)
for ev in SEEDF:
    sd = standings(os.path.join(REPO, SEEDF[ev])); prev = None
    for st in (1, 2, 3):
        rs = [r for r in rows if r["event"] == ev and r["stage"] == st]; nms = sorted({r["a"] for r in rs} | {r["b"] for r in rs})
        pre = {}
        for r in rs: pre[r["a"]] = r["ra"]; pre[r["b"]] = r["rb"]          # pre-stage Valve points used in the fit
        if st == 1: tl = [Team(i + 1, n, i + 1, float(pre[n])) for i, n in enumerate(sorted(nms, key=lambda n: sd[n][0]))]
        else:
            adv = {t.name for t in prev.values() if t.wins == 3}
            tl = seed_next_stage(prev, [InvitedTeam(n, sd[n][0], float(pre[n])) for n in nms if n not in adv])
            tl = [Team(t.id, t.name, t.seed, float(pre[t.name])) for t in tl]
        idn = {t.name: t.id for t in tl}
        locked = {frozenset((idn[r["a"]], idn[r["b"]])): idn[r["a"] if r["y"] else r["b"]] for r in rs}
        prev = simulate_stage([Team(t.id, t.name, t.seed, t.rating) for t in tl], None, 400.0, np.random.default_rng(0), locked, pairings_out=[])
        actual = {i: (t.wins, t.losses) for i, t in prev.items()}
        bo3 = (ev == "Cologne 2026" and st == 3)
        for S_pts in (600, 1410):
            sel = run_mc(tl, None, float(S_pts), 20000, seed=7, all_bo3=bo3); card = optimize(sel, tl).recommended; del sel
            e = run_mc(tl, None, float(S_pts), 20000, seed=8, all_bo3=bo3); h = hits(card, e.sample); del e
            real = int(hits(card, [actual])[0])
            res[S_pts].append((ev, st, float(np.mean(h >= 5)), float(h.mean()), real))
for S_pts, L in res.items():
    print(f"  spread {S_pts}: " + "; ".join(f"{e.split()[0][:3]} S{s}: pred {p:.2f}, got {r}" for e, s, p, m, r in L))
    pred = np.mean([x[2] for x in L]); got = np.mean([x[4] >= 5 for x in L])
    print(f"     mean predicted P>=5 {pred:.3f} vs realized {sum(x[4]>=5 for x in L)}/9 = {got:.3f}; mean predicted hits {np.mean([x[3] for x in L]):.2f} vs realized {np.mean([x[4] for x in L]):.2f}")
    # exact tail prob of the realized count under the stated probabilities (Poisson-binomial by simulation)
    sim = (np.random.default_rng(3).random((200000, 9)) < np.array([x[2] for x in L])).sum(1)
    print(f"     P(count of >=5 stages <= realized | model) = {np.mean(sim <= sum(x[4]>=5 for x in L)):.3f}")
