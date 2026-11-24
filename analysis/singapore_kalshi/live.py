"""Condition Singapore tournament futures on PGL's completed matches and price ten-lots."""

import hashlib
import json
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from math import comb, log
from typing import NamedTuple

import httpx
import numpy as np

from engine.bracket import GF_FEEDERS, QF_SEEDS, SF_FEEDERS, simulate_bracket
from engine.montecarlo import wilson
from engine.probs import p_map
from engine.seeding import InvitedTeam, seed_next_stage, seed_playoffs
from engine.swiss import simulate_stage
from engine.teams import Team, load_stage

from .model import EARLIER, HERE, POINTS, ROOT, D, fit, name, walk
from .paper import BASE, get, now, pack, roster_check

PGL = "https://news.pglesports.com/api/"
# Invitation seed order published on PGL's Singapore tournament page.
INVITES = (
    ("FUT", "Nemiga", "G2", "1win", "Natus Vincere", "Astralis", "The MongolZ", "MIBR"),
    ("MOUZ", "Vitality", "FURIA", "Aurora", "Spirit", "BETBOOM", "Falcons", "Legacy"),
)
EVENTS = {
    "stage2": "KXCS2QUALIFIERS-26PGLSGS2",
    "stage3": "KXCS2QUALIFIERS-26PGLSGS3",
    "playoffs": "KXCS2QUALIFIERS-26PGLSGPO",
    "champion": "KXCS2-PGLSG26",
}
RUNS = 10_000
SEED = 20261124


class Game(NamedTuple):
    slot: int | str
    a: str
    b: str
    winner: str | None
    bo: int
    left: int
    right: int
    start: str


def fixtures(client):
    stages, live = [], set()
    for stage in range(1, 5):
        rows = (
            get(client, PGL + "playoffsEndpoint")
            if stage == 4
            else get(client, PGL + "groupStageEndpoint", stage=stage)
        )
        if len(rows) != (8 if stage == 4 else 33):
            raise ValueError(f"PGL stage {stage} fixture count changed")
        games = []
        for m in rows:
            a, b = name(m["leftTeam"]), name(m["rightTeam"])
            if not a or not b:
                if m["status"] in ("live", "end"):
                    raise ValueError("Missing participant in a started fixture")
                continue
            if a == b or {a, b} - POINTS.keys():
                raise ValueError(f"Unrecognized PGL fixture: {a}, {b}")
            label = m["round"].strip().lower()
            if stage == 4:
                slot = label
                expected = "BO5" if label == "final" else "BO3"
            else:
                slot = (
                    1
                    if label.startswith("opening round")
                    else int(re.match(r"round (\d)", label)[1])
                )
                expected = (
                    "BO3"
                    if stage == 3 or slot > 3 or (slot == 3 and "mid" not in label)
                    else "BO1"
                )
            if expected != m["format"]:
                raise ValueError(f"PGL format changed for {label}: {m['format']}")
            start = datetime.strptime(f"{m['date']} {m['time']}", "%d.%m.%Y %H:%M")
            if m["timeZone"] != "SGT":
                raise ValueError("Review PGL fixture time zone")
            start = start.replace(tzinfo=timezone(timedelta(hours=8)))
            winner = None
            left, right = m["leftScore"], m["rightScore"]
            target = int(expected[-1]) // 2 + 1
            if m["status"] == "end":
                if max(left, right) != target or left == right:
                    raise ValueError(f"Confirm the official result for {a} vs {b}")
                winner = a if left > right else b
            elif m["status"] not in ("upcoming", "live"):
                raise ValueError(f"Review PGL status {m['status']}")
            elif m["status"] == "live" or now() >= start:
                live.update((a, b))
                if max(left, right) >= target:
                    raise ValueError(f"Waiting for PGL to confirm {a} vs {b}")
            games.append(
                Game(
                    slot,
                    a,
                    b,
                    winner,
                    int(expected[-1]),
                    left,
                    right,
                    start.isoformat(),
                )
            )
        stages.append(sorted(games))
    return stages, live


def series_inputs(teams, games, spread):
    ids = {t.name: t.id for t in teams}
    ratings = {t.name: t.rating for t in teams}
    locks, overrides = {}, {}
    for g in games:
        if g.winner:
            locks[frozenset((ids[g.a], ids[g.b]))] = ids[g.winner]
        elif g.left or g.right:
            # First to a majority. Count completions of the remaining maps at the same map prior.
            need = g.bo // 2 + 1 - g.left
            remaining = g.bo - g.left - g.right
            p = p_map(ratings[g.a], ratings[g.b], spread)
            win = sum(
                comb(remaining, k) * p**k * (1 - p) ** (remaining - k)
                for k in range(need, remaining + 1)
            )
            a, b = ids[g.a], ids[g.b]
            overrides[f"{min(a, b)}-{max(a, b)}"] = win if a < b else 1 - win
    return locks, overrides


def check_pairs(teams, games, rounds):
    names = {t.id: t.name for t in teams}
    for game in games:
        pairs = rounds[game.slot]
        if not any({names[i] for i in pair} == {game.a, game.b} for pair in pairs):
            raise ValueError(
                f"PGL draw differs from simulation at {game.slot}: {game.a} vs {game.b}"
            )


def simulate(stages, points, spread, n, seed=SEED):
    field, _ = load_stage(ROOT / "data/singapore2026/stage1.json")
    invites = [
        [InvitedTeam(team, i, points[team]) for i, team in enumerate(group, 1)]
        for group in INVITES
    ]
    counts = {k: Counter() for k in EVENTS}
    rng = np.random.default_rng(seed)
    for _ in range(n):
        teams = [Team(t.id, name(t.name), t.seed, points[name(t.name)]) for t in field]
        for stage, outcome in enumerate(("stage2", "stage3", "playoffs")):
            games = stages[stage]
            pairs = []
            locks, overrides = series_inputs(teams, games, spread)
            finals = simulate_stage(
                teams,
                None,
                spread,
                rng,
                locks,
                market_overrides=overrides,
                pairings_out=pairs,
                all_bo3=stage == 2,
            )
            check_pairs(teams, games, dict(enumerate(pairs, 1)))
            counts[outcome].update(t.name for t in finals.values() if t.wins == 3)
            teams = (
                seed_next_stage(finals, invites[stage])
                if stage < 2
                else seed_playoffs(finals)
            )
        games = stages[3]
        locks, overrides = series_inputs(teams, games, spread)
        winners = simulate_bracket(
            teams, None, spread, rng, locks, market_overrides=overrides
        )
        if games:
            pairs = {
                f"quarter final match {i}": [QF_SEEDS[f"QF{i}"]] for i in range(1, 5)
            }
            losers = []
            for i, (a, b) in enumerate(SF_FEEDERS.values(), 1):
                pair = (winners[a], winners[b])
                pairs[f"semi-final match {i}"] = [pair]
                losers.append(next(t for t in pair if t != winners[f"SF{i}"]))
            pairs["final"] = [[winners[label] for label in GF_FEEDERS]]
            pairs["third place decider"] = [losers]
            check_pairs(teams, games, pairs)
        counts["champion"][next(t.name for t in teams if t.id == winners["GF"])] += 1
    return {k: {t: row[t] for t in points} for k, row in counts.items()}


def forecast(db, stages, roster, model):
    earlier = {team: row["points"] for team, row in EARLIER.items()}
    scenarios = [(POINTS, model["fitted"]), (earlier, model["fitted"])]
    scenarios.extend((POINTS, spread) for spread in model["spread90"])
    five = json.loads((HERE / "rosters.json").read_text(encoding="utf8"))["five"]
    if five.keys() != POINTS.keys():
        raise ValueError("Reviewed roster sheet must cover all 32 teams")
    changed = {
        t
        for t in five
        if {p.casefold() for p in five[t]} != {p.casefold() for p in EARLIER[t]["five"]}
    }
    # Stress the org-level prior for changed lineups in both directions. The historical
    # residual sets a scenario width, not a fitted player effect.
    width = model["fitted"] * model["residual80"] / log(10)
    if changed:
        for sign in (-1, 1):
            adjusted = {
                t: p + sign * width if t in changed else p for t, p in POINTS.items()
            }
            scenarios.append((adjusted, model["fitted"]))
    state = {
        "stages": stages,
        "roster": roster,
        "five": five,
        "scenarios": scenarios,
        "invites": INVITES,
        "fixture": json.loads((ROOT / "data/singapore2026/stage1.json").read_text())[
            "teams"
        ],
        "n": RUNS,
        "seed": SEED,
        "version": 2,
    }
    signature = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    cached = db.execute(
        "SELECT estimates FROM forecasts WHERE id=?", (signature,)
    ).fetchone()
    if cached:
        return signature, json.loads(cached[0]), False
    draws = [simulate(stages, points, spread, RUNS) for points, spread in scenarios]
    estimates = {}
    for outcome in EVENTS:
        estimates[outcome] = {}
        for team in POINTS:
            samples = [d[outcome][team] for d in draws]
            estimates[outcome][team] = [
                samples[0] / RUNS,
                wilson(min(samples), RUNS)[0],
                wilson(max(samples), RUNS)[1],
            ]
    with db:
        db.execute(
            "INSERT OR IGNORE INTO forecasts VALUES(?,?,?,?,?)",
            (
                signature,
                now().isoformat(),
                json.dumps(state),
                json.dumps(estimates),
                RUNS,
            ),
        )
    return signature, estimates, True


def futures(client, estimates, live, reviewed):
    clauses = {
        "champion": "is the 2026 PGL Major Singapore champion",
        "playoffs": "is one of the teams to reach the PGL Major Singapore 2026 playoffs",
        "stage2": "is one of the teams to reach Stage 2 of PGL Major Singapore 2026",
        "stage3": "is one of the teams to reach Stage 3 of PGL Major Singapore 2026",
    }
    markets = []
    for outcome, event in EVENTS.items():
        series = event.split("-")[0]
        info = get(client, BASE + "/series/" + series)["series"]
        if info["fee_type"] not in ("quadratic", "quadratic_with_maker_fees"):
            raise ValueError(f"Review fee schedule for {series}")
        for m in get(client, BASE + "/events/" + event)["markets"]:
            if m["status"] == "active":
                if (
                    m["event_ticker"] != event
                    or m["market_type"] != "binary"
                    or D(m["notional_value_dollars"]) != 1
                ):
                    raise ValueError(f"Review terms for {m['ticker']}")
                expected = f"If {m['yes_sub_title']} {clauses[outcome]}, then the market resolves to Yes."
                if m["rules_primary"].strip().casefold() != expected.casefold():
                    raise ValueError(f"Review settlement wording for {m['ticker']}")
                markets.append((outcome, m, D(str(info["fee_multiplier"]))))

    def price(item):
        outcome, m, mult = item
        team, ticker = name(m["yes_sub_title"]), m["ticker"]
        p, lo, hi = estimates[outcome][team]
        url = BASE + "/markets/" + ticker + "/orderbook"
        for attempt in range(5):
            response = client.get(url)
            if response.status_code != 429 or attempt == 4:
                response.raise_for_status()
                break
            delay = response.headers.get("retry-after", "")
            time.sleep(float(delay) if delay.isdigit() else 2**attempt)
        book = response.json()["orderbook_fp"]
        observed = now().isoformat()
        yes = walk(book.get("no_dollars") or [], mult)
        no = walk(book.get("yes_dollars") or [], mult)
        spread = yes["ask_c"] + no["ask_c"] - 100 if yes and no else None
        rows = []
        for side, fair, floor, fill in (("yes", p, lo, yes), ("no", 1 - p, 1 - hi, no)):
            if fill:
                cost = fill["debit_usd"] / fill["qty"]
                rows.append(
                    {
                        "side": side,
                        "fill": fill,
                        "net_c": 100 * (fair - cost),
                        "low_net_c": 100 * (floor - cost),
                        "candidate": reviewed
                        and team not in live
                        and spread is not None
                        and -1e-8 <= spread <= 5.000001
                        and floor > cost,
                    }
                )
        return {
            "ticker": ticker,
            "team": team,
            "outcome": outcome,
            "at": observed,
            "fair": [p, lo, hi],
            "spread_c": spread,
            "rules": [m["rules_primary"], m["rules_secondary"]],
            "book": book,
            "sides": rows,
        }

    observations = []
    for item in markets:
        observations.append(price(item))
        time.sleep(0.10)
    return observations


def main():
    # Keep immutable observations separate from the pre-match entry ledger.
    with (
        sqlite3.connect(HERE / "live.sqlite3", timeout=60) as db,
        httpx.Client(timeout=25) as client,
    ):
        db.executescript("""
            CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY, at TEXT, state TEXT, estimates TEXT, n INTEGER);
            CREATE TABLE IF NOT EXISTS markets(at TEXT PRIMARY KEY, forecast TEXT, snapshot BLOB);
        """)
        stages, live = fixtures(client)
        roster, changed = roster_check(client)
        key, estimates, refreshed = forecast(db, stages, roster, fit())
        books = futures(client, estimates, live, not changed)
        latest, latest_live = fixtures(client)
        if (
            latest != stages
            or latest_live != live
            or roster_check(client) != (roster, changed)
        ):
            raise RuntimeError(
                "Tournament state changed during the scan. Run again for current prices."
            )
        at = now().isoformat()
        with db:
            db.execute(
                "INSERT INTO markets VALUES(?,?,?)",
                (
                    at,
                    key,
                    pack(
                        {
                            "books": books,
                            "live": sorted(live),
                            "roster_reviewed": not changed,
                        }
                    ),
                ),
            )
        print(
            json.dumps(
                {
                    "at": at,
                    "refreshed": refreshed,
                    "forecast": key,
                    "simulations_per_scenario": RUNS,
                    "completed": [
                        [g.a, g.b, g.winner]
                        for stage in stages
                        for g in stage
                        if g.winner
                    ],
                    "live": sorted(live),
                    "roster_reviewed": not changed,
                    "markets": len(books),
                    "candidates": [
                        [b["ticker"], s["side"], s["net_c"], s["low_net_c"]]
                        for b in books
                        for s in b["sides"]
                        if s["candidate"]
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
