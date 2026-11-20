"""Score Singapore Stage 1 forecasts after the stage ends (stdlib only).

Usage:  python score_singapore.py results.json forecast_a.json [forecast_b.json ...]
results.json maps every team to its final record, for example {"NIP": "3-1", "GOSH": "0-3", ...}.
Each forecast is a file in the repo's data/singapore2026/forecast.json schema.

Pre-registered reading (fixed on 2026-11-20, before any match):
  1. Card: count correct picks; the card "passes" at 5 or more.
  2. Per-team log loss over four outcomes (3-0, 3-1 or 3-2, 0-3, other). Lower is better.
     Baseline = base rates (2/16, 6/16, 2/16, 6/16), which scores 1.2555.
  3. Head to head: the forecast with the lower log loss wins. One stage is 16 correlated
     observations, so a difference under about 0.05 is noise and settles nothing.
"""
import json, math, sys

def bucket(rec):
    w, l = (int(x) for x in rec.split("-"))
    return "sweep" if (w, l) == (3, 0) else "advance_pick" if w == 3 else "winless" if (w, l) == (0, 3) else "other"

def main(argv):
    results = json.load(open(argv[1])); truth = {t: bucket(r) for t, r in results.items()}
    counts = {b: sum(v == b for v in truth.values()) for b in ("sweep", "advance_pick", "winless", "other")}
    if len(truth) != 16 or counts != {"sweep": 2, "advance_pick": 6, "winless": 2, "other": 6}:
        sys.exit(f"results are not a complete 16-team Swiss stage: {counts}")
    base = {"sweep": 2 / 16, "advance_pick": 6 / 16, "winless": 2 / 16, "other": 6 / 16}
    print(f"base-rate log loss: {-sum(math.log(base[b]) for b in truth.values()) / 16:.4f}")
    for path in argv[2:]:
        f = json.load(open(path)); card = f["card"]
        hit = (sum(truth[t] == "sweep" for t in card["3-0"]) + sum(truth[t] == "advance_pick" for t in card["3-1 or 3-2"])
               + sum(truth[t] == "winless" for t in card["0-3"]))
        ll = 0.0; brier_q = 0.0
        for row in f["teams"]:
            p = {"sweep": row["sweep"], "advance_pick": row["advance_pick"], "winless": row["winless"]}
            p["other"] = 1 - sum(p.values()); b = truth[row["team"]]
            ll -= math.log(max(p[b], 1e-6)); brier_q += (row["qualify"] - (b in ("sweep", "advance_pick"))) ** 2
        print(f"{path}: card {hit}/10 ({'PASS' if hit >= 5 else 'MISS'}); stated P(>=5) {f['evaluation']['p_ge5']:.3f}; "
              f"per-team log loss {ll / 16:.4f}; qualify Brier {brier_q / 16:.4f}")

if __name__ == "__main__":
    main(sys.argv)
