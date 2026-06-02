"""One-off: reproduce the app's market-anchored run and dump the REAL distribution of
correct ballot picks (0..10) across every simulated tournament, for the public page chart.

Mirrors app.py exactly: FIXED_SEED, S=40, N=100000, ratings back-solved from
data/odds_cache.json, market_blend feeding the epistemic outer loop.
"""
import json
import numpy as np

from engine.teams import load_teams
from engine.backsolve import fit_ratings, invert_series
from engine.montecarlo import run_mc
from engine.optimizer import optimize, build_outcome_matrices, COIN_THRESHOLD
from ui.odds_loader import load_odds_cache

FIXED_SEED = 20260528
S = 40.0
N = 100_000

teams = load_teams()
ids = [t.id for t in teams]
name = {t.id: t.name for t in teams}

cache = load_odds_cache() or {}
blended = cache.get("blended") or {}
targets, market_blend = {}, {}
for key, b in blended.items():
    lo, hi = (int(x) for x in key.split("-"))
    p = float(b["p"]); var = float(b.get("var", 0.0)); bo3 = bool(b.get("bo3", False))
    targets[(lo, hi)] = invert_series(p, bo3)
    market_blend[key] = (p, var)

anchor_id = min(ids)
ratings = fit_ratings(targets, teams, S, anchor_id) if targets else None
mb = market_blend or None

print(f"[run] N={N} seed={FIXED_SEED} S={S} odds-fed={mb is not None} "
      f"priced_matches={len(market_blend)}")
result = run_mc(teams, ratings, S, N, {}, seed=FIXED_SEED, market_blend=mb)
ntot = result.n
print(f"[run] total sims (incl. epistemic draws) = {ntot}")

from engine.optimizer import Ballot, p_ge5

opt = optimize(result, teams)
is_30, is_adv, is_03 = build_outcome_matrices(result.sample, ids)
mats = (is_30, is_adv, is_03)

by_name = {t.name: t.id for t in teams}
# The PUBLIC PAGE ballot = the user's Reddit-post call.
post = Ballot(
    picks_30=(by_name["GamerLegion"], by_name["HEROIC"]),
    picks_adv=(by_name["NRG"], by_name["MIBR"], by_name["BetBoom"],
               by_name["B8"], by_name["TYLOO"], by_name["M80"]),
    picks_03=(by_name["THUNDER dOWNUNDER"], by_name["FlyQuest"]),
)
b = post  # score the POST ballot for the page chart

rows = ([is_30[t] for t in b.picks_30]
        + [is_adv[t] for t in b.picks_adv]
        + [is_03[t] for t in b.picks_03])
correct = np.sum(rows, axis=0)
hist = [int(np.sum(correct == k)) for k in range(11)]
dist = [h / ntot for h in hist]
pge5 = float(np.mean(correct >= COIN_THRESHOLD))

# transparency: engine's own auto-recommended ballot + its P(>=5)
rec = opt.recommended
print(f"[ballot] PAGE/post P(>=5) = {pge5*100:.2f}%  E[correct]={correct.mean():.3f}")
print(f"[ballot] engine auto-recommended P(>=5) = {opt.recommended_pge5*100:.2f}%  "
      f"30={[name[t] for t in rec.picks_30]} adv={[name[t] for t in rec.picks_adv]} "
      f"03={[name[t] for t in rec.picks_03]}")

p_adv_q = result.p_advance()
p_30_m = result.p_30()
p_03_m = result.p_03()

out = {
    "n_total": int(ntot),
    "N": N,
    "k_epistemic": int(round(ntot / N)),
    "seed": FIXED_SEED,
    "pge5": pge5,
    "pge5_recommended": opt.recommended_pge5,
    "e_correct": float(correct.mean()),
    "dist": [round(x, 6) for x in dist],
    "hist": hist,
    "ballot": {
        "p30": [name[t] for t in b.picks_30],
        "adv": [name[t] for t in b.picks_adv],
        "p03": [name[t] for t in b.picks_03],
    },
    # per-team marginals to verify this run matches the page's displayed numbers
    "marginals_qualify_advance": {name[t]: round(p_adv_q[t] * 100, 1) for t in ids},
    "marginals_30": {name[t]: round(p_30_m[t] * 100, 1) for t in ids},
    "marginals_03": {name[t]: round(p_03_m[t] * 100, 1) for t in ids},
}
print("=== RESULT JSON ===")
print(json.dumps(out, indent=2))
