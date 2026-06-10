"""One-off: the Stage-3 call-my-shot run from LIVE market odds (2026-06-09 re-fetch).

Mirrors the app's stage-3 odds-fed Run exactly — same seed, same S, same K=12 epistemic
outer loop, all-Bo3 — but headless, reading the freshly-fetched data/odds_cache.json:
  - blended  = live Kalshi KXCS2GAME R1 series prices (bo3-stamped, priced directly in-sim),
  - fitted_ratings = scripts.fit_qualify output calibrated to the live KXCS2QUALIFIERS
    playoff-qualify mids (the market's rounds-2-5 view), used INSTEAD of the R1 back-solve
    (QFIT-03 — identical precedence to app._odds_from_cache).

Run:  uv run python -m scripts.predict_stage3
"""
import json

from engine.teams import load_stage
from engine.montecarlo import run_mc
from engine.optimizer import optimize
from ui.odds_loader import load_odds_cache
from ui.state import FIXED_SEED

S = 40.0
N = 200_000

teams, cfg = load_stage("data/stage3.json")
assert cfg.get("all_bo3") is True
ids = [t.id for t in teams]
name = {t.id: t.name for t in teams}

cache = load_odds_cache() or {}
assert cache.get("_meta", {}).get("stage") == 3, "cache must be the stage-3 fetch"
blended = cache.get("blended") or {}
market_blend = {k: (float(b["p"]), float(b.get("var", 0.0))) for k, b in blended.items()}

fitted = {int(k): float(v) for k, v in (cache.get("fitted_ratings") or {}).items()}
assert sorted(fitted) == sorted(ids), "fitted_ratings must cover exactly the 16 stage-3 ids"

print(f"[run] N={N} seed={FIXED_SEED} S={S} all_bo3=True priced_R1={len(market_blend)} "
      f"qualify_fit={cache['_meta'].get('qualify_fit', {}).get('converged')}")
result = run_mc(teams, fitted, S, N, {}, seed=FIXED_SEED, market_blend=market_blend,
                all_bo3=True)
print(f"[run] total sims (incl. epistemic draws) = {result.n}")

p30, padv, p03 = result.p_30(), result.p_advance(), result.p_03()
print(f"[invariants] sum P(adv)={sum(padv.values()):.3f} sum P(3-0)={sum(p30.values()):.3f} "
      f"sum P(0-3)={sum(p03.values()):.3f}")

print("\n| Team | P(advance) | P(3-0) | P(0-3) |")
print("|---|---:|---:|---:|")
for tid in sorted(ids, key=lambda t: -padv[t]):
    print(f"| {name[tid]} | {padv[tid]*100:.1f}% | {p30[tid]*100:.1f}% | {p03[tid]*100:.1f}% |")

opt = optimize(result, teams)
b = opt.recommended
fmt = lambda picks: ", ".join(name[t] for t in picks)
print(f"\nBallot A (E[correct]-optimal, E={opt.e_correct_a:.2f}, P(>=5)={opt.pge5_a*100:.1f}%):")
print(f"  3-0: {fmt(opt.ballot_a.picks_30)} | adv: {fmt(opt.ballot_a.picks_adv)} | "
      f"0-3: {fmt(opt.ballot_a.picks_03)}")
print(f"Ballot B (P(>=5)-optimal, E={opt.e_correct_b:.2f}, P(>=5)={opt.pge5_b*100:.1f}%):")
print(f"  3-0: {fmt(opt.ballot_b.picks_30)} | adv: {fmt(opt.ballot_b.picks_adv)} | "
      f"0-3: {fmt(opt.ballot_b.picks_03)}")
print(f"diff: {[name[t] for t in opt.diff]} | warning: {opt.warning}")
print(f"\nRECOMMENDED P(>=5/10) = {opt.recommended_pge5*100:.1f}%")

with open("data/_stage3_forecast_live.json", "w", encoding="utf-8") as f:
    json.dump({
        "fetched_at": cache["_meta"]["fetched_at"],
        "n_sims": result.n,
        "table": {name[t]: {"adv": padv[t], "p30": p30[t], "p03": p03[t]} for t in ids},
        "ballot": {"picks_30": [name[t] for t in b.picks_30],
                   "picks_adv": [name[t] for t in b.picks_adv],
                   "picks_03": [name[t] for t in b.picks_03]},
        "p_ge5": opt.recommended_pge5,
    }, f, indent=2)
print("[saved] data/_stage3_forecast_live.json")
