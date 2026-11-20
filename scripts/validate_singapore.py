"""Replay independently recorded stages and compare fixed, pre-event strength models."""
import csv
import gzip
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

from engine.probs import series_prob
from engine.swiss import simulate_stage
from engine.teams import ADVANCE_AT_WINS, ELIMINATE_AT_LOSSES, Team
from odds.base import devig_fixed_two_way
from scripts.singapore_stage1 import CARRIES, FIXTURE, SPREAD, model_inputs

EVIDENCE = FIXTURE.parent / "evidence"
AUDIT = EVIDENCE / "validation.json"
FORM = "Recent maps"
MODELS = ["Ratings only", *CARRIES, FORM]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fit_form(label, cutoff):
    """Ridge-regularized Bradley–Terry on map winners, with a 30-day half-life."""
    with gzip.open(EVIDENCE / f"{label}-maps.csv.gz", "rt") as f:
        rows = list(csv.DictReader(f))
    ids, inverse = np.unique([[int(r["winner_id"]), int(r["loser_id"])] for r in rows], return_inverse=True)
    winners, losers = inverse.reshape(-1, 2).T
    ages = np.array([(cutoff - datetime.fromisoformat(r["finished_utc"])).total_seconds() / 86400 for r in rows])
    if min(ages) <= 0 or max(ages) > 60 or len({r["map_id"] for r in rows}) != len(rows):
        raise ValueError(f"Out-of-window or duplicate map in {label}")
    weights = 0.5 ** (ages / 30)
    s = np.zeros(len(ids))
    for _ in range(4000):
        p = 1 / (1 + np.exp(s[losers] - s[winners]))
        residual = weights * (1 - p)
        curvature = residual * p
        gradient = np.bincount(winners, residual, len(s)) - np.bincount(losers, residual, len(s)) - 2 * s
        diagonal = np.bincount(winners, curvature, len(s)) + np.bincount(losers, curvature, len(s)) + 2
        step = 0.5 * gradient / diagonal
        s += step
        if max(abs(step)) < 1e-9:
            break
    else:
        raise ValueError("Map strength fit did not converge")
    counts = np.bincount(winners, minlength=len(s)) + np.bincount(losers, minlength=len(s))
    return dict(zip(ids, s * SPREAD / math.log(10))), dict(zip(ids, counts.tolist()))


def replay(teams, matches):
    ids = {t.name: t.id for t in teams}

    def pair(m):
        return frozenset(ids[name] for name in m["teams"])

    locked = {pair(m): ids[m["winner"]] for m in matches}
    actual = []
    simulate_stage(teams, None, SPREAD, np.random.default_rng(0), locked, pairings_out=actual)
    records = {t.name: [0, 0] for t in teams}
    checks = []
    for rnd, pairs in enumerate(actual, 1):
        expected = {pair(m) for m in matches if m["round"] == rnd}
        if set(pairs) != expected:
            raise ValueError(f"Round {rnd} differs from published draw: {expected ^ set(pairs)}")
        for match in (m for m in matches if m["round"] == rnd):
            a, b = match["teams"]
            wins, losses = records[a]
            expected_bo = 3 if wins == ADVANCE_AT_WINS - 1 or losses == ELIMINATE_AT_LOSSES - 1 else 1
            if records[a] != records[b] or match["bo"] != expected_bo:
                raise ValueError(f"Published series format or record group differs for {a}–{b}")
            winner = match["winner"]
            loser = b if winner == a else a
            records[winner][0] += 1
            records[loser][1] += 1
        checks.append(len(expected))
    if checks != [8, 8, 8, 6, 3]:
        raise ValueError(f"Incomplete replay: {checks}")
    return checks


def metrics(winner_probs):
    p = np.array(winner_probs)
    return dict(n=len(p), log_loss=float(-np.log(p).mean()), brier=float(np.mean((1 - p) ** 2)))


def validate():
    stages = read(EVIDENCE / "historical-stages.json")
    windows = read(EVIDENCE / "map-sources.json")["windows"]
    summary = {}
    for label, stage in stages.items():
        teams = [Team(t["seed"], t["name"], t["seed"], t["vrs"] / 10) for t in stage["teams"]]
        by_name = {t.name: t for t in teams}
        replayed = replay(teams, stage["matches"])
        strengths, counts = fit_form(label, datetime.fromisoformat(windows[label]["before_utc"]))
        form = {t["name"]: strengths.get(t["id"], 0.0) for t in stage["teams"]}
        openers = []
        for q in stage["openers"]:
            a, b = sorted(q["teams"], key=lambda n: by_name[n].seed)
            probability = (devig_fixed_two_way(*q["decimal"]) if "decimal" in q else (q["bid"] + q["ask"]) / 2)
            if not math.isclose(probability, q["p"]):
                raise ValueError(f"Archived raw price differs from the stored probability for {a}–{b}")
            p = probability if a == q["teams"][0] else 1 - probability
            openers.append(dict(teams=[a, b], bid=p, ask=p))
            observed = q.get("observed") or stage["price_source"]["edition_time"]
            if datetime.fromisoformat(observed) >= datetime.fromisoformat(stage["lock_schedule"]):
                raise ValueError(f"Post-start price: {label}, {a}")
        result = {}
        for model in MODELS:
            ratings, prices = model_inputs(teams, openers, model, form)
            ratings = ratings or {t.id: t.rating for t in teams}
            observations = []
            for match in stage["matches"]:
                a, b = sorted([by_name[n] for n in match["teams"]], key=lambda t: t.seed)
                quoted = prices[f"{a.id}-{b.id}"][0] if prices and match["round"] == 1 else None
                p = series_prob(ra=ratings[a.id], rb=ratings[b.id], bo3=match["bo"] == 3, S=SPREAD, market_series_prob=quoted)
                observations.append((match["round"], p if a.name == match["winner"] else 1 - p))
            result[model] = {
                "all": metrics([p for _, p in observations]),
                "later": metrics([p for rnd, p in observations if rnd > 1]),
            }
        summary[label] = dict(replayed=replayed, scores=result,
                              maps_by_team={t["name"]: counts.get(t["id"], 0) for t in stage["teams"]})
    # Choose the challenger on the first two events. Confirm direction on the third.
    candidates = ["Opener only", "Half carry", "Full carry", FORM]
    candidate = min(candidates, key=lambda m: sum(summary[e]["scores"][m]["later"]["log_loss"] for e in ("austin", "budapest")))

    def beats_base(event, metric):
        scores = summary[event]["scores"]
        return scores[candidate]["later"][metric] < scores["Opener only"]["later"][metric]

    confirmed = all(beats_base(e, "log_loss") for e in stages) and beats_base("cologne", "brier")
    chosen = candidate if confirmed else "Opener only"
    rosters = read(EVIDENCE / "singapore-rosters.json")
    strengths, counts = fit_form("singapore", datetime.fromisoformat(windows["singapore"]["before_utc"]))
    return dict(events=summary, development_candidate=candidate, chosen=chosen,
                singapore_form={name: strengths.get(i, 0.0) for name, i in rosters["team_ids"].items()},
                singapore_map_counts={name: counts.get(i, 0) for name, i in rosters["team_ids"].items()})


if __name__ == "__main__":
    result = validate()
    AUDIT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for e, data in result["events"].items():
        print(e, data["replayed"], {k: (round(v["later"]["log_loss"], 4), round(v["later"]["brier"], 4)) for k, v in data["scores"].items()})
    print("Development candidate:", result["development_candidate"], "Selected:", result["chosen"])
