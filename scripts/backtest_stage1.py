"""scripts/backtest_stage1.py — score the model's PRE-EVENT Stage-1 predictions vs the
ACTUAL Cologne 2026 Stage-1 result (finished 2026-06-05).

Pre-event predictions = the RATING-ONLY MC on data/stage1.json's [INFERRED] priors
(no odds were ever captured: odds_fetch.log shows matches=0 and there is no
data/odds_cache.json), so this is the honest rating-only baseline the app would have
shown. We score three things:

  1. The model's PER-TEAM probabilities P(3-0)/P(advance)/P(0-3) via Brier + log-loss,
     against the realized binary outcomes, compared to a base-rate ("climatology")
     baseline. This is the real calibration test.
  2. The ENGINE's auto-recommended 2/6/2 ballot vs reality (correct/10).
  3. The USER's posted Reddit ballot vs reality (correct/10).

Cologne scoring (memory: cologne-advance-pick-3-1-3-2): a 3-0 pick scores iff the team
finished 3-0; an ADVANCE pick scores iff the team finished 3-1 OR 3-2 (NOT 3-0, NOT
eliminated); a 0-3 pick scores iff the team finished 0-3.

Run: uv run python -m scripts.backtest_stage1
"""
from __future__ import annotations

import math

from engine.teams import load_teams
from engine.montecarlo import run_mc
from engine.optimizer import optimize, Ballot

FIXED_SEED = 20260528  # mirrors app.py / dump_distribution.py
S = 40.0
N = 100_000

# --- ACTUAL Stage-1 final records (verified vs Liquipedia + HLTV + Hotspawn/EGW) ---
FINAL_RECORD = {
    "B8": "3-0", "BetBoom": "3-0",
    "GamerLegion": "3-1", "M80": "3-1", "MIBR": "3-1",
    "TYLOO": "3-2", "BIG": "3-2", "FlyQuest": "3-2",
    "Liquid": "2-3", "NRG": "2-3", "Lynn Vision": "2-3",
    "THUNDER dOWNUNDER": "1-3", "Sharks": "1-3", "HEROIC": "1-3",
    "SINNERS": "0-3", "Gaimin Gladiators": "0-3",
}
ADVANCED = {n for n, r in FINAL_RECORD.items() if r.startswith("3-")}
WENT_30 = {n for n, r in FINAL_RECORD.items() if r == "3-0"}
WENT_03 = {n for n, r in FINAL_RECORD.items() if r == "0-3"}
SCORES_ADV_PICK = {n for n, r in FINAL_RECORD.items() if r in ("3-1", "3-2")}


def brier(probs: dict[int, float], positives: set[int]) -> float:
    return sum((p - (1.0 if tid in positives else 0.0)) ** 2 for tid, p in probs.items()) / len(probs)


def logloss(probs: dict[int, float], positives: set[int]) -> float:
    tot = 0.0
    for tid, p in probs.items():
        p = min(1 - 1e-15, max(1e-15, p))
        y = 1.0 if tid in positives else 0.0
        tot += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return tot / len(probs)


def climatology_brier(positives: set[int], n: int) -> float:
    """Brier of the trivial 'predict the base rate for everyone' forecaster."""
    base = len(positives) / n
    return base * (1 - base)  # mean((base - y)^2) over n teams with len(positives) ones


def score_ballot(ballot: Ballot, name: dict[int, str]) -> tuple[int, list[str]]:
    detail = []
    correct = 0
    for tid in ballot.picks_30:
        ok = name[tid] in WENT_30
        correct += ok
        detail.append(f"  3-0  {name[tid]:<20} {FINAL_RECORD[name[tid]]:<4} {'HIT' if ok else 'miss'}")
    for tid in ballot.picks_adv:
        ok = name[tid] in SCORES_ADV_PICK
        correct += ok
        nm = name[tid]
        why = "" if ok else (" (3-0 doesn't score an advance pick)" if nm in WENT_30 else "")
        detail.append(f"  adv  {nm:<20} {FINAL_RECORD[nm]:<4} {'HIT' if ok else 'miss'}{why}")
    for tid in ballot.picks_03:
        ok = name[tid] in WENT_03
        correct += ok
        detail.append(f"  0-3  {name[tid]:<20} {FINAL_RECORD[name[tid]]:<4} {'HIT' if ok else 'miss'}")
    return correct, detail


def main() -> None:
    teams = load_teams()
    ids = [t.id for t in teams]
    name = {t.id: t.name for t in teams}
    by_name = {t.name: t.id for t in teams}

    pos_adv = {by_name[n] for n in ADVANCED}
    pos_30 = {by_name[n] for n in WENT_30}
    pos_03 = {by_name[n] for n in WENT_03}

    print(f"[run] RATING-ONLY  N={N} seed={FIXED_SEED} S={S} (no odds captured pre-event)")
    result = run_mc(teams, None, S, N, {}, seed=FIXED_SEED)
    p_adv, p_30, p_03 = result.p_advance(), result.p_30(), result.p_03()

    print("\n=== PER-TEAM: model P(advance) vs reality (sorted by model) ===")
    print(f"{'team':<22}{'P(adv)':>8}{'P(3-0)':>8}{'P(0-3)':>8}   actual")
    for tid in sorted(ids, key=lambda i: -p_adv[i]):
        nm = name[tid]
        flag = "ADV" if nm in ADVANCED else "out"
        print(f"{nm:<22}{p_adv[tid]*100:7.1f}%{p_30[tid]*100:7.1f}%{p_03[tid]*100:7.1f}%   {FINAL_RECORD[nm]:<4} {flag}")

    print("\n=== CALIBRATION (Brier / log-loss; lower is better) ===")
    for label, probs, pos in (("advance", p_adv, pos_adv), ("3-0", p_30, pos_30), ("0-3", p_03, pos_03)):
        b = brier(probs, pos)
        ll = logloss(probs, pos)
        bc = climatology_brier(pos, len(ids))
        skill = 1 - b / bc if bc else float("nan")
        print(f"  {label:<9} Brier={b:.4f}  (base-rate={bc:.4f}, skill={skill:+.2%})  logloss={ll:.4f}")

    # Hits/misses on the binary call: did the model's top-8 P(advance) match the real top 8?
    model_top8 = {name[i] for i in sorted(ids, key=lambda i: -p_adv[i])[:8]}
    print(f"\n  model top-8 by P(advance): {sorted(model_top8)}")
    print(f"  actually advanced (8):     {sorted(ADVANCED)}")
    print(f"  top-8 hits: {len(model_top8 & ADVANCED)}/8  misses: {sorted(model_top8 - ADVANCED)} (in) vs {sorted(ADVANCED - model_top8)} (out)")

    # --- Ballot scoring ---
    opt = optimize(result, teams)
    print("\n=== ENGINE auto-recommended ballot vs reality ===")
    rec_correct, rec_detail = score_ballot(opt.recommended, name)
    print("\n".join(rec_detail))
    print(f"  ENGINE ballot: {rec_correct}/10 correct  (coin needs >=5)")

    post = Ballot(
        picks_30=(by_name["GamerLegion"], by_name["HEROIC"]),
        picks_adv=(by_name["NRG"], by_name["MIBR"], by_name["BetBoom"],
                   by_name["B8"], by_name["TYLOO"], by_name["M80"]),
        picks_03=(by_name["THUNDER dOWNUNDER"], by_name["FlyQuest"]),
    )
    print("\n=== USER's posted Reddit ballot vs reality ===")
    post_correct, post_detail = score_ballot(post, name)
    print("\n".join(post_detail))
    print(f"  USER ballot: {post_correct}/10 correct  (coin needs >=5)")


if __name__ == "__main__":
    main()
