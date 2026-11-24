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

A ratings-only simulator (Valve points, spread 1,410, no match prices) runs alongside as the
comparison. Data: ``data/cologne_bt.json.gz`` (fetched by ``data/fetch_cologne_bt.py``).

    uv run --frozen python -m analysis.singapore_live.backtest_cologne
"""

from __future__ import annotations

import bisect
import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np

from engine.montecarlo import run_mc
from engine.teams import Team, load_stage

from .price import S, fit_strengths

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE / "data" / "cologne_bt.json.gz"
VALVE = ROOT / "analysis" / "pr18_review" / "major_swiss_matches.json"
FIXTURES = {1: ROOT / "data" / "stage1.json", 2: ROOT / "data" / "stage2.json"}
STEP = 900
N = 3000
FEE = 0.05
RATINGS_SPREAD = 141.0  # 1,410 Valve points per tenfold odds, the best ratings-only fit
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


def settled_at(series: Series, start: int) -> int:
    """First minute after which the match price stays outside [0.03, 0.97] for good."""
    last_open = None
    for t, p in zip(series.t, series.p):
        if t >= start - 3600 and 0.03 <= p <= 0.97:
            last_open = t
    after = [t for t in series.t if last_open is None or t > last_open]
    return after[0] if after else series.t[-1]


def stage_inputs(stage, data, valve):
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
    matches, wins, losses = [], {n: 0 for n in known}, {n: 0 for n in known}
    for r in rows:
        a, b = canon(r["a"], known), canon(r["b"], known)
        m = poly[frozenset((a, b))]
        first = canon(m["outcomes"][0], known)
        series = Series([(t, p if first == a else 1 - p) for t, p in m["hist"]])
        winner = a if r["y"] else b
        final = series.p[-1]
        if (final > 0.5) != (winner == a):
            raise ValueError(f"Polymarket's final price disagrees with Valve's result for {a} vs {b}")
        matches.append({"a": a, "b": b, "bo": 3 if r["bo3"] else 1, "winner": winner, "round": r["round"],
                        "start": m["start"], "created": m["created"], "series": series,
                        "end": settled_at(series, m["start"])})
        wins[winner] += 1
        losses[b if winner == a else a] += 1
    outcome = {n: int(wins[n] == 3) for n in known}
    return teams, by, matches, outcome


def replay(stage, data, valve):
    teams, by, matches, outcome = stage_inputs(stage, data, valve)
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
    ids = [t.id for t in teams]
    prior = {t.id: t.rating for t in teams}
    out = []
    for k, t in enumerate(range(begin - begin % STEP + STEP, end, STEP)):
        locks, overrides, obs = {}, {}, []
        record = {n: [0, 0] for n in known}
        for m in matches:
            a, b = by[m["a"]], by[m["b"]]
            if t >= m["end"]:
                locks[frozenset((a.id, b.id))] = by[m["winner"]].id
                record[m["winner"]][0] += 1
                record[m["b"] if m["winner"] == m["a"] else m["a"]][1] += 1
                pre = m["series"].at(m["start"])
                if pre is not None:
                    obs.append((a.id, b.id, pre, m["bo"]))
            elif t >= m["created"]:
                now, pre = m["series"].at(t), m["series"].at(min(t, m["start"]))
                if now is not None:
                    lo, hi = sorted((a.id, b.id))
                    overrides[f"{lo}-{hi}"] = now if a.id == lo else 1 - now
                if pre is not None:
                    obs.append((a.id, b.id, pre, m["bo"]))
        open_teams = [n for n in known if n in markets and 3 not in record[n] and t >= markets[n]["created"]]
        if not open_teams:
            continue
        strengths = fit_strengths(teams, obs, 1.0, 0.3)
        fed = run_mc(teams, strengths, S, N, locks, seed=1000 + k, market_blend={x: (v, 0.0) for x, v in overrides.items()})
        rated = run_mc(teams, prior, RATINGS_SPREAD, N, locks, seed=5000 + k)
        q_fed = {i: c / N for i, c in fed.counts_advance.items()}
        q_rat = {i: c / N for i, c in rated.counts_advance.items()}
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


def main():
    cache = HERE / "data" / "cologne_bt_rows.json"
    if cache.exists() and "--recompute" not in sys.argv:
        rows = json.loads(cache.read_text())
    else:
        data = json.loads(gzip.open(DATA).read())
        valve = json.loads(VALVE.read_text())
        rows = replay(1, data, valve) + replay(2, data, valve)
        cache.write_text(json.dumps(rows))
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
                se = pnl.std(ddof=1) / math.sqrt(len(pnl)) if len(pnl) > 1 else float("nan")
                print(f"{src:<8} {theta:.2f}   {h:.2f}        {len(tr):>4}  {sum(x['pnl'] > 0 for x in tr):>3}   {pnl.mean():+.3f}          ({se:.3f})          {pnl.sum():+.2f}")
    detail = trades(rows, "fed", 0.05, 0.02)
    print("\nMarket-fed trades at theta 0.05, half-spread 0.02:")
    for x in detail:
        print(f"  stage {x['stage']} {x['team']:<18} {x['side']:<3} cost {x['cost']:.3f} fair {x['fair']:.3f} pnl {x['pnl']:+.3f} {'(match live)' if x['live'] else ''}")
    return report


if __name__ == "__main__":
    sys.exit(main() and 0)
