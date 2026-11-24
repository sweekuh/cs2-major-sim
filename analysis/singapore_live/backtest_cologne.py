"""Backtest the live pricer's idea on IEM Cologne 2026: price qualify markets off match markets.

Polymarket ran "Qualify to Stage 2" (opened June 4, before Stage 1 round 4) and "Qualify to
Stage 3" (through all of Stage 2). Every 15 minutes this replay rebuilds the Swiss state from
what was known then: finished matches become locks, drawn matches use their Polymarket price at
that minute, and strengths for undrawn rounds are fitted to the match prices seen so far.
The simulator's qualification probability is then compared with the qualify market's price.

Three checks, all using only information available at each step:
1. Accuracy against the final outcome (log loss, Brier), averaged per team.
2. Price discovery: does the qualify market move toward the simulator within the next hour?
3. Paper trades: buy the side the simulator favors when the gap beats an assumed half-spread
   plus Polymarket's taker fee by a threshold; one entry per team side, held to settlement.

A ratings-only simulator (Valve points, spread fitted on earlier Majors) runs alongside as the
comparison. Data: ``data/cologne_bt.json.gz`` (fetched by ``data/fetch_cologne_bt.py``).

    uv run --frozen python -m analysis.singapore_live.backtest_cologne
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

from engine.montecarlo import run_mc
from engine.teams import Team, load_stage
from analysis.singapore_kalshi.model import fit

from .price import S, fit_strengths

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE / "data" / "cologne_bt.json.gz"
MATCH_TIMES = HERE / "data" / "cologne_match_times.json"
VALVE = ROOT / "analysis" / "pr18_review" / "major_swiss_matches.json"
FIXTURES = {1: ROOT / "data" / "stage1.json", 2: ROOT / "data" / "stage2.json"}
STEP = 900
N = 3000
FEE = 0.05
ALIAS = {"fut": "FUT Esports", "betboom team": "BetBoom", "heroic": "HEROIC", "sinners": "SINNERS"}


def canon(name: str, known: set[str]) -> str:
    key = name.strip().casefold()
    for k in known:
        if k.casefold() == key:
            return k
    if key in ALIAS and ALIAS[key] in known:
        return ALIAS[key]
    raise KeyError(f"Unknown Cologne team {name!r}")


class Series:
    def __init__(self, points):
        self.t = [p[0] for p in points]
        self.p = [p[1] for p in points]

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return self.p[i] if i >= 0 else None


def stage_inputs(stage, data, valve, match_times):
    template, _ = load_stage(FIXTURES[stage])
    known = {t.name for t in template}
    rows = [r for r in valve if r["event"] == "Cologne 2026" and r["stage"] == stage]
    points = {}
    for r in rows:
        points[canon(r["a"], known)] = r["ra"]
        points[canon(r["b"], known)] = r["rb"]
    teams = [Team(t.id, t.name, t.seed, points[t.name] / 10) for t in template]
    by = {t.name: t for t in teams}
    poly = {frozenset(canon(o, known) for o in m["outcomes"]): m for m in data["matches"] if m["stage"] == stage}
    clocks = {frozenset(canon(o, known) for o in m["teams"]): m for m in match_times if m["stage"] == stage}
    if clocks.keys() != poly.keys() or len(clocks) != len(rows) or len(rows) != 33:
        raise ValueError(f"Incomplete match clock coverage for Cologne stage {stage}")
    matches, wins, losses = [], {n: 0 for n in known}, {n: 0 for n in known}
    for r in rows:
        a, b = canon(r["a"], known), canon(r["b"], known)
        m = poly[frozenset((a, b))]
        clock = clocks[frozenset((a, b))]
        start = math.ceil(datetime.fromisoformat(clock["start"]).timestamp())
        end = math.ceil(datetime.fromisoformat(clock["finish"]).timestamp())
        if start >= end:
            raise ValueError(f"Invalid clock for {a} vs {b}")
        first = canon(m["outcomes"][0], known)
        series = Series([(t, p if first == a else 1 - p) for t, p in m["hist"]])
        winner = a if r["y"] else b
        if canon(clock["winner"], known) != winner:
            raise ValueError(f"Timed match result disagrees with Valve for {a} vs {b}")
        final = series.p[-1]
        if (final > 0.5) != (winner == a):
            raise ValueError(f"Polymarket's final price disagrees with Valve's result for {a} vs {b}")
        matches.append({"a": a, "b": b, "bo": 3 if r["bo3"] else 1, "winner": winner, "round": r["round"],
                        "start": start, "created": m["created"], "series": series, "end": end})
        wins[winner] += 1
        losses[b if winner == a else a] += 1
    outcome = {n: int(wins[n] == 3) for n in known}
    return teams, by, matches, outcome


def state_at(t, matches, by):
    """Predictor inputs through t. Even a 99.9% match quote cannot reveal a winner."""
    locks, overrides, obs = {}, {}, []
    record = {n: [0, 0] for n in by}
    for m in matches:
        a, b = by[m["a"]], by[m["b"]]
        if t >= m["end"]:
            winner = m["winner"]
            locks[frozenset((a.id, b.id))] = by[winner].id
            record[winner][0] += 1
            record[m["b"] if winner == m["a"] else m["a"]][1] += 1
        if t < m["created"]:
            continue
        if t < m["end"]:
            now = m["series"].at(t)
            if now is not None:
                lo, hi = sorted((a.id, b.id))
                overrides[f"{lo}-{hi}"] = now if a.id == lo else 1 - now
        pre = m["series"].at(min(t, m["start"]))
        if pre is not None:
            obs.append((a.id, b.id, pre, m["bo"]))
    return record, locks, overrides, obs


def simulate_tick(job):
    teams, locks, overrides, obs, spread, k = job
    strengths = fit_strengths(teams, obs, 1.0, 0.3)
    fed = run_mc(teams, strengths, S, N, locks, seed=1000 + k,
                 market_blend={x: (v, 0.0) for x, v in overrides.items()})
    prior = {team.id: team.rating for team in teams}
    rated = run_mc(teams, prior, spread, N, locks, seed=5000 + k)
    return ({i: c / N for i, c in fed.counts_advance.items()},
            {i: c / N for i, c in rated.counts_advance.items()})


def replay(stage, data, valve, match_times, spread, pool=None):
    teams, by, matches, outcome = stage_inputs(stage, data, valve, match_times)
    known = set(by)
    markets = {}
    for r in data["qualify"][str(stage)]:
        try:
            team = canon(r["team"], known)
        except KeyError:
            continue  # a team from another stage (decided before this stage starts)
        markets[team] = {"series": Series(r["hist"]), "created": r["created"], "volume": r["volume"],
                         "result": int(float(json.loads(r["result"])[0]) > 0.5) if isinstance(r["result"], str) else int(float(r["result"][0]) > 0.5)}
        if markets[team]["result"] != outcome[team]:
            raise ValueError(f"Qualify market for {team} settled against Valve's record")
    begin = max(min(m["created"] for m in markets.values()), min(m["start"] for m in matches) - 12 * 3600)
    end = max(m["end"] for m in matches)
    ticks, jobs = [], []
    for k, t in enumerate(range(begin - begin % STEP + STEP, end, STEP)):
        record, locks, overrides, obs = state_at(t, matches, by)
        open_teams = [n for n in sorted(markets) if 3 not in record[n] and t >= markets[n]["created"]]
        if not open_teams:
            continue
        ticks.append((t, open_teams))
        jobs.append((teams, locks, overrides, obs, spread, k))
    results = pool.map(simulate_tick, jobs) if pool is not None else map(simulate_tick, jobs)
    out = []
    for (t, open_teams), (q_fed, q_rat) in zip(ticks, results, strict=True):
        for n in open_teams:
            price = markets[n]["series"].at(t)
            if price is None:
                continue
            out.append({"stage": stage, "t": t, "team": n, "market": price,
                        "fed": q_fed[by[n].id], "ratings": q_rat[by[n].id],
                        "later": markets[n]["series"].at(t + 3600), "outcome": outcome[n],
                        "live": any(m["start"] <= t < m["end"] and n in (m["a"], m["b"]) for m in matches)})
    return out


def loss(p, y):
    p = min(max(p, 0.005), 0.995)
    return -math.log(p if y else 1 - p)


def summarize(rows):
    teams = sorted({(r["stage"], r["team"]) for r in rows})
    per = {}
    for key in teams:
        rs = [r for r in rows if (r["stage"], r["team"]) == key]
        per[key] = {src: np.mean([loss(r[src], r["outcome"]) for r in rs]) for src in ("market", "fed", "ratings")}
        per[key]["brier"] = {src: np.mean([(r[src] - r["outcome"]) ** 2 for r in rs]) for src in ("market", "fed", "ratings")}
    report = {"steps": len(rows), "team_markets": len(teams)}
    for src in ("fed", "ratings"):
        d = np.array([per[k][src] - per[k]["market"] for k in teams])
        report[f"logloss_{src}_minus_market"] = (round(float(d.mean()), 4), round(float(d.std(ddof=1) / math.sqrt(len(d))), 4))
    report["logloss_mean"] = {src: round(float(np.mean([per[k][src] for k in teams])), 4) for src in ("market", "fed", "ratings")}
    report["brier_mean"] = {src: round(float(np.mean([per[k]["brier"][src] for k in teams])), 4) for src in ("market", "fed", "ratings")}
    # Price discovery: regress the next hour's move on the current gap, with a team-cluster bootstrap.
    rd = [r for r in rows if r["later"] is not None]
    rng = np.random.default_rng(7)
    for src in ("fed", "ratings"):
        gap = np.array([r[src] - r["market"] for r in rd])
        move = np.array([r["later"] - r["market"] for r in rd])
        slope = float(gap @ move / (gap @ gap))
        keys = [(r["stage"], r["team"]) for r in rd]
        groups = [[i for i, kk in enumerate(keys) if kk == k] for k in sorted(set(keys))]
        boots = []
        for _ in range(2000):
            pick = [i for j in rng.integers(0, len(groups), len(groups)) for i in groups[j]]
            g, mv = gap[pick], move[pick]
            boots.append(g @ mv / (g @ g))
        report[f"discovery_slope_{src}"] = (round(slope, 3), [round(float(np.percentile(boots, q)), 3) for q in (5, 95)])
        report[f"mean_abs_gap_{src}"] = round(float(np.mean(np.abs(gap))), 4)
    return report


def joint_discovery(rows, seed=11):
    """Next-hour qualify-market move regressed on both gaps plus reversal of the last 15 minutes.

    Noise in the market price alone makes any gap look predictive (the price snaps back), so the
    reversal term absorbs bounce and the ratings gap absorbs plain mean reversion. Returns the
    coefficients with 90% team-cluster bootstrap intervals, for all steps and split by whether
    the team's own match was live.
    """
    idx = {(r["stage"], r["team"], r["t"]): r for r in rows}
    rng = np.random.default_rng(seed)
    sel = [r for r in rows if r["later"] is not None and (r["stage"], r["team"], r["t"] - STEP) in idx]

    def fit(part):
        X = np.array([[r["fed"] - r["market"], r["ratings"] - r["market"],
                       idx[(r["stage"], r["team"], r["t"] - STEP)]["market"] - r["market"]] for r in part])
        y = np.array([r["later"] - r["market"] for r in part])
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        keys = sorted({(r["stage"], r["team"]) for r in part})
        groups = [[i for i, r in enumerate(part) if (r["stage"], r["team"]) == k] for k in keys]
        boots = np.array([np.linalg.lstsq(X[p], y[p], rcond=None)[0] for p in
                          ([i for j in rng.integers(0, len(groups), len(groups)) for i in groups[j]] for _ in range(1500))])
        return {name: [round(float(beta[k]), 3), round(float(np.percentile(boots[:, k], 5)), 3),
                       round(float(np.percentile(boots[:, k], 95)), 3)]
                for k, name in enumerate(("fed_gap", "ratings_gap", "reversal"))} | {"steps": len(part)}

    return {"all": fit(sel), "team_match_live": fit([r for r in sel if r["live"]]),
            "no_team_match_live": fit([r for r in sel if not r["live"]])}


def trades(rows, src, theta, half_spread):
    entered, out = set(), []
    for r in sorted(rows, key=lambda r: r["t"]):
        f, m = r[src], r["market"]
        for side, fair, px in (("yes", f, m + half_spread), ("no", 1 - f, 1 - m + half_spread)):
            key = (r["stage"], r["team"], side)
            if key in entered or not 0.01 <= px <= 0.99:
                continue
            cost = px + FEE * px * (1 - px)
            if fair - cost >= theta:
                entered.add(key)
                payoff = r["outcome"] if side == "yes" else 1 - r["outcome"]
                out.append({"team": r["team"], "stage": r["stage"], "side": side, "t": r["t"], "cost": cost,
                            "fair": fair, "pnl": payoff - cost, "live": r["live"]})
    return out


def clustered_trade_se(entries):
    """Bootstrap the pooled per-share mean, resampling whole stage/team markets."""
    groups = {}
    for row in entries:
        groups.setdefault((row["stage"], row["team"]), []).append(row["pnl"])
    if len(groups) < 2:
        return float("nan")
    clusters = [groups[k] for k in sorted(groups)]
    totals = np.array([sum(group) for group in clusters])
    counts = np.array([len(group) for group in clusters])
    sample = np.random.default_rng(23).integers(len(clusters), size=(5000, len(clusters)))
    means = totals[sample].sum(axis=1) / counts[sample].sum(axis=1)
    return float(means.std(ddof=1))


def replay_key(spread):
    """Legacy caches lack a fingerprint and cannot supply replay rows."""
    inputs = [Path(__file__), DATA, MATCH_TIMES, VALVE, *FIXTURES.values(), HERE / "price.py",
              *(ROOT / "engine" / filename for filename in ("montecarlo.py", "swiss.py", "teams.py", "probs.py"))]
    digest = hashlib.sha256(str((spread, STEP, N)).encode())
    for path in inputs:
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--workers", type=int, default=1, help="Parallel simulation workers for an uncached replay")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    spread = fit(before_event="Cologne 2026")["fitted"] / 10
    print(f"Prior-Majors ratings spread: {spread * 10:g} Valve points", flush=True)
    fingerprint = replay_key(spread)
    cache = HERE / "data" / "cologne_bt_rows.json"
    saved = json.loads(cache.read_text()) if cache.exists() and not args.recompute else None
    if isinstance(saved, dict) and saved.get("fingerprint") == fingerprint:
        rows = saved["rows"]
    else:
        data = json.loads(gzip.open(DATA).read())
        valve = json.loads(VALVE.read_text())
        times = json.loads(MATCH_TIMES.read_text())["matches"]
        rows = []
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for stage in (1, 2):
                rows.extend(replay(stage, data, valve, times, spread, pool))
                print(f"Completed stage {stage}: {len(rows)} cumulative team observations", flush=True)
        cache.write_text(json.dumps({"fingerprint": fingerprint, "rows": rows}))
    report = summarize(rows)
    report["joint_discovery"] = joint_discovery(rows)
    for label, keep in (("team_match_live", True), ("no_team_match_live", False)):
        part = [r for r in rows if r["live"] == keep]
        keys = sorted({(r["stage"], r["team"]) for r in part})
        d = [np.mean([loss(r["fed"], r["outcome"]) - loss(r["market"], r["outcome"])
                      for r in part if (r["stage"], r["team"]) == k]) for k in keys]
        report[f"logloss_fed_minus_market_{label}"] = (round(float(np.mean(d)), 4), round(float(np.std(d, ddof=1) / math.sqrt(len(d))), 4))
    for key, value in report.items():
        if key == "joint_discovery":
            for part, coef in value.items():
                print(f"joint_discovery[{part}]: {json.dumps(coef)}")
        else:
            print(f"{key}: {json.dumps(value)}")
    print("\nPaper trades held to settlement (one per team side):")
    print("model    theta  half-spread  trades  won  mean P&L/share  (team-cluster SE)  total per share")
    for src in ("fed", "ratings"):
        for theta in (0.03, 0.05, 0.08):
            for h in (0.01, 0.02, 0.03):
                tr = trades(rows, src, theta, h)
                if not tr:
                    print(f"{src:<8} {theta:.2f}   {h:.2f}          0")
                    continue
                pnl = np.array([x["pnl"] for x in tr])
                se = clustered_trade_se(tr)
                print(f"{src:<8} {theta:.2f}   {h:.2f}        {len(tr):>4}  {sum(x['pnl'] > 0 for x in tr):>3}   {pnl.mean():+.3f}          ({se:.3f})          {pnl.sum():+.2f}")
    detail = trades(rows, "fed", 0.05, 0.02)
    print("\nMarket-fed trades at theta 0.05, half-spread 0.02:")
    for x in detail:
        print(f"  stage {x['stage']} {x['team']:<18} {x['side']:<3} cost {x['cost']:.3f} fair {x['fair']:.3f} pnl {x['pnl']:+.3f} {'(match live)' if x['live'] else ''}")
    return report


if __name__ == "__main__":
    sys.exit(main() and 0)
