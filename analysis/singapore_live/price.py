"""Price Singapore Stage 1 derivative markets off the liquid match markets. Paper only.

Liquid match-winner prices (Polymarket first, Kalshi as fallback) go straight into the
Swiss simulator for every drawn match, including matches in progress. Team strengths for
rounds not yet drawn are fitted to all observed match prices, so the only model input that
is not a market price is the shape of later rounds. The simulator then values the thin
markets that depend on several matches: Polymarket's 3-0 / 3-1 / 3-2 / 0-3 and "qualify to
Stage 2" lists, and Kalshi's "reach Stage 2" futures.

A paper entry is logged when buying one side at the displayed book, after the taker fee,
beats the least favorable fair value across the strength scenarios by ``EDGE_MIN``. The first
entry per market side is frozen after rechecking the fixture state and executable book.
At a map break a missing match quote uses the remaining maps and the pre-match strength.
During a map, missing match odds hold the stage forecast because every team's future draw
can depend on that result.

    uv run --frozen python -m analysis.singapore_live.price            # print the table
    uv run --frozen python -m analysis.singapore_live.price --grade    # settle entries from PGL
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

from engine.montecarlo import run_mc
from engine.probs import p_map
from engine.swiss import simulate_stage
from engine.teams import Team, build_round1_pairs, load_stage

from . import feed, markets as mk
from .watch import STATE, append
from analysis.singapore_kalshi.model import SIZE as KALSHI_SIZE, walk as kalshi_walk

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data/singapore2026/stage1.json"
CARD = ROOT / "data/singapore2026/forecast.json"
S = 60.0  # engine rating units are 10 Valve points; strengths are fitted on this scale
N_SIMS = 20_000
SEED = 20261125
POLY_SHARES = 20
EDGE_MIN = 0.02
EDGE_MIN_MAPS = 0.05  # exploratory family, not part of the pre-registered test
PAPER_VENUES = {"kalshi"}  # the user trades on Kalshi only; Polymarket is a read-only price input
# (prior scale, ridge weight): how far undrawn-round strengths lean on Nov 19 points.
SCENARIOS = {"base": (1.0, 0.3), "flat_prior": (0.5, 0.3), "sticky": (1.0, 2.0), "flat_sticky": (0.5, 2.0)}
RECORDS = {"3-0": [(3, 0)], "3-1": [(3, 1)], "3-2": [(3, 2)], "0-3": [(0, 3)],
           "qualify": [(3, 0), (3, 1), (3, 2)]}


def now():
    return datetime.now(timezone.utc)


def bo3_to_map(p: float) -> float:
    """Invert the best-of-three closed form p^2 (3 - 2p)."""
    lo, hi = 1e-9, 1 - 1e-9
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if mid * mid * (3 - 2 * mid) < p else (lo, mid)
    return (lo + hi) / 2


def fit_strengths(teams, observations, scale, lam):
    """Ridge fit of map strengths (engine units) to observed series prices.

    observations: list of (id_a, id_b, P(a wins series), best_of). Each price becomes a
    target strength gap S * log10(odds) at map level; the prior is Nov 19 Valve points,
    shrunk toward the field mean by ``scale``, with weight ``lam`` per team.
    """
    ids = [t.id for t in teams]
    pos = {i: k for k, i in enumerate(ids)}
    prior = np.array([t.rating for t in teams])
    prior = prior.mean() + scale * (prior - prior.mean())
    A = lam * np.eye(len(ids))
    b = lam * prior.copy()
    for a, c, p, bo in observations:
        p = min(max(p, 0.01), 0.99)
        pm = bo3_to_map(p) if bo == 3 else p
        y = S * math.log10(pm / (1 - pm))
        i, j = pos[a], pos[c]
        A[i, i] += 1; A[j, j] += 1; A[i, j] -= 1; A[j, i] -= 1
        b[i] += y; b[j] -= y
    x = np.linalg.solve(A, b)
    return {i: float(x[pos[i]]) for i in ids}


def closing_price(client, cache: dict, slug: str, token: str, start: str) -> float | None:
    """Last Polymarket price at or before the (actual) start, cached per market."""
    if slug in cache:
        return cache[slug]
    t0 = int(datetime.fromisoformat(start).timestamp())
    try:
        hist = mk._json(client, "GET", f"{mk.CLOB}/prices-history",
                        params={"market": token, "startTs": t0 - 4 * 3600, "endTs": t0 + 60, "fidelity": 1})
    except httpx.HTTPError:
        return None
    pts = [h for h in hist.get("history", []) if h["t"] <= t0]
    cache[slug] = pts[-1]["p"] if pts else None
    return cache[slug]


def map_score_probs(s_a: float, r: float, score: tuple[int, int]) -> dict:
    """Best-of-three map-score probabilities for team A from the live series price.

    ``s_a`` is A's current series price, ``r`` A's per-map probability on a fresh map (from the
    pre-match price). The map in progress gets whatever probability ``q`` reconciles ``s_a`` with
    fresh maps at ``r``; using one per-map probability for both would misprice a mid-map state.
    """
    a, b = score
    r = min(max(r, 1e-4), 1 - 1e-4)
    s = min(max(s_a, 0.0), 1.0)
    clamp = lambda x: min(max(x, 0.0), 1.0)
    if (a, b) == (0, 0):
        q = clamp((s - r * r) / (2 * r * (1 - r)))
        return {"sweep_a": q * r, "sweep_b": (1 - q) * (1 - r), "over": 1 - q * r - (1 - q) * (1 - r)}
    if (a, b) == (1, 0):
        q = clamp((s - r) / (1 - r))
        return {"sweep_a": q, "sweep_b": 0.0, "over": 1 - q}
    if (a, b) == (0, 1):
        q = clamp(s / r)
        return {"sweep_a": 0.0, "sweep_b": 1 - q, "over": q}
    if (a, b) == (1, 1):
        return {"sweep_a": 0.0, "sweep_b": 0.0, "over": 1.0}
    return {"sweep_a": float((a, b) == (2, 0)), "sweep_b": float((a, b) == (0, 2)), "over": float(a + b == 3)}


def fixture_map_markets(f, k_maps, km):
    """Kalshi map-score rows for this fixture only.

    Map markets share the event suffix of the KXCS2GAME listing (``...-26NOV250530TLNIP``), and
    that listing is already bound to the PGL fixture by teams, settlement wording and kickoff.
    Without a bound listing the fixture gets no map markets, so a rematch can never borrow them.
    """
    listing = km.get(f.key)
    if not listing or "event" not in listing:
        return []
    suffix = listing["event"].split("-", 1)[1]
    return [m for m in k_maps.get(frozenset((f.a, f.b)), []) if m.get("event", "").split("-", 1)[-1] == suffix]


def records(sample, ids):
    arr = np.array([[s[i] for i in ids] for s in sample], dtype=np.int8)  # (n, teams, 2)
    out = {}
    for k, i in enumerate(ids):
        w, l = arr[:, k, 0], arr[:, k, 1]
        out[i] = {fam: float(np.mean(np.any([(w == a) & (l == b) for a, b in recs], axis=0)))
                  for fam, recs in RECORDS.items()}
    return out, arr


def check_draw(teams, locks, overrides, fixtures, ids):
    """The engine's pairings must reproduce every drawn PGL round whose inputs are settled."""
    pairs = []
    simulate_stage([Team(t.id, t.name, t.seed, t.rating) for t in teams], None, S,
                   np.random.default_rng(0), dict(locks), pairings_out=pairs, market_overrides=overrides)
    names = {t.id: t.name for t in teams}
    finished = {f.round for f in fixtures if f.status == "end"}
    for rnd in sorted({f.round for f in fixtures if f.a and f.b}):
        if rnd > 1 and not all(r in finished for r in range(1, rnd)):
            continue
        pgl = {frozenset((f.a, f.b)) for f in fixtures if f.round == rnd and f.a and f.b}
        engine = {frozenset(names[i] for i in p) for p in pairs[rnd - 1]} if rnd - 1 < len(pairs) else set()
        if not pgl <= engine:
            raise ValueError(f"PGL round {rnd} draw differs from the engine: {sorted(map(sorted, pgl - engine))}")


def taker_cost_poly(book, shares, rate):
    if not book:
        return None
    left, cost, fee = shares, 0.0, 0.0
    for price, size in book["asks"]:
        take = min(size, left)
        cost += take * price
        fee += mk.poly_fee(price, take, rate)
        left -= take
        if left <= 1e-9:
            return {"avg": cost / shares, "unit": (cost + fee) / shares, "shares": shares}
    return None


def in_play(f):
    return f.status != "end" and (
        f.status == "live" or any(f.score) or any(a or b for _, a, b in f.maps)
    )


def at_map_break(f):
    if f.bo != 3 or f.score not in ((1, 0), (0, 1), (1, 1)):
        return False
    finished = sum(f.score)
    if len(f.maps) <= finished or any(a or b for _, a, b in f.maps[finished:]):
        return False
    completed = f.maps[:finished]
    if any(max(a, b) < 13 or abs(a - b) < 2 for _, a, b in completed):
        return False
    return (sum(a > b for _, a, b in completed), sum(b > a for _, a, b in completed)) == f.score


def remaining_bo3(score, map_win):
    if score == (1, 0):
        return 1 - (1 - map_win) ** 2
    if score == (0, 1):
        return map_win ** 2
    if score == (1, 1):
        return map_win
    raise ValueError(f"Not a BO3 map break: {score}")


def match_quote(f, info, books, km):
    if info and not info["closed"] and info["accepting"] and info["bo"] == f.bo:
        mid = mk.poly_mid(books.get(info["tokens"][0]))
        if mid is not None:
            return (mid if info["outcomes"][0] == f.a else 1 - mid), "polymarket"
    if f.key in km:
        bid, ask = km[f.key]["quotes"][f.a]
        if 0 < bid < ask < 1 and ask - bid <= 0.10:
            return (bid + ask) / 2, "kalshi"
    return None, None


def kalshi_cost(book, side, multiplier):
    levels = book.get("no_dollars" if side == "yes" else "yes_dollars") or []
    fill = kalshi_walk(levels, multiplier)
    if fill:
        return {"avg": fill["ask_c"] / 100, "unit": fill["debit_usd"] / fill["qty"], "shares": fill["qty"]}
    return None


def confirm_signals(client, candidates, fx, live_probs, initial_terms):
    """Refresh the candidate books and confirm the simulated stage state still applies."""
    if not candidates:
        return [], None
    wants_poly = any(s["venue"] == "polymarket" for s in candidates)
    wants_kalshi = any(s["venue"] == "kalshi" and s.get("family") != "maps" for s in candidates)
    wants_maps = any(s.get("family") == "maps" for s in candidates)
    events = mk.poly_events(client) if wants_poly or live_probs else []
    terms = {}
    if wants_poly:
        terms.update({("polymarket", m["market"]): m for m in mk.poly_derivatives(events)
                      if not m["closed"] and m["accepting"]})
    multiplier = None
    if wants_kalshi:
        kalshi, multiplier = mk.kalshi_s2(client)
        terms.update({("kalshi", m["market"]): m for m in kalshi if m["status"] == "active"})
    maps_multiplier = None
    if wants_maps:
        maps_multiplier = mk.kalshi_series_multiplier(client, "KXCS2TOTALMAPS")
        terms.update({("kalshi", m["market"]): m for rows in mk.kalshi_bo3_markets(client).values()
                      for m in rows if m["status"] == "active"})

    verified = []
    for signal in candidates:
        key = signal["venue"], signal["market"]
        original, fresh = initial_terms[key], terms.get(key)
        if fresh and all(original.get(k) == fresh.get(k)
                         for k in ("family", "team", "rules", "question", "tokens", "kind", "label")):
            verified.append((signal, fresh))
    if not verified:
        return [], "Candidate markets closed or changed terms"

    live_fx = [fx[key] for key in live_probs]
    matches = mk.poly_matches(events) if live_fx else {}
    match_info = {f.key: matches.get((f.stage, frozenset((f.a, f.b)))) for f in live_fx}
    tokens = {s["token"] for s, _ in verified if s["venue"] == "polymarket"}
    tokens.update(m["tokens"][0] for m in match_info.values() if m and not m["closed"] and m["accepting"])
    books = mk.poly_books(client, sorted(tokens)) if tokens else {}
    poly_at = now().isoformat()
    if live_fx:
        km = mk.kalshi_matches(client, live_fx)
        for f in live_fx:
            p, _ = match_quote(f, match_info[f.key], books, km)
            if p != live_probs[f.key]:
                return [], "A live match price changed during the scan"

    confirmed = []
    kalshi_books = {}
    for signal, market in verified:
        if signal["venue"] == "polymarket":
            cost = taker_cost_poly(books.get(signal["token"]), signal["shares"], market["fee_rate"])
            quote_at = poly_at
        else:
            ticker = market["market"]
            if ticker not in kalshi_books:
                book = mk.kalshi_book(client, ticker)
                kalshi_books[ticker] = book, now().isoformat()
            book, quote_at = kalshi_books[ticker]
            cost = kalshi_cost(book, signal["side"], maps_multiplier if signal.get("family") == "maps" else multiplier)
        threshold = EDGE_MIN_MAPS if signal.get("family") == "maps" else EDGE_MIN
        if cost and signal["worst_fair"] - cost["unit"] >= threshold:
            confirmed.append({**signal, "avg": round(cost["avg"], 4), "unit_cost": round(cost["unit"], 4),
                              "edge": round(signal["worst_fair"] - cost["unit"], 4), "quote_observed_at": quote_at})
    # Read the official state *after* every book. Stage-wide Swiss derivatives depend
    # on other teams' matches as well as the contract team's own score.
    checked, _ = feed.fetch(client, (1,))
    state_at = now().isoformat()
    if checked != fx:
        return [], "PGL fixtures or scores changed during the scan"
    return [{**s, "worst_fair": round(s["worst_fair"], 4), "at": state_at, "state_observed_at": state_at}
            for s in confirmed], None


def snapshot(reason: str, quiet: bool = False) -> dict:
    teams, _ = load_stage(FIXTURE)
    by_name = {t.name: t for t in teams}
    ids = [t.id for t in teams]
    at = now()
    STATE.mkdir(exist_ok=True)
    cache_path = STATE / "closing.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    with httpx.Client(timeout=25) as client:
        fx, updated = feed.fetch(client, (1,))
        fixtures = [f for f in fx.values() if f.a and f.b]
        for f in fixtures:
            if f.a not in by_name or f.b not in by_name:
                raise KeyError(f"Stage 1 fixture has an unknown team: {f.a} vs {f.b}")
        r1 = {frozenset((x.name, y.name)) for x, y in build_round1_pairs(teams)}
        if {frozenset((f.a, f.b)) for f in fixtures if f.round == 1} != r1:
            raise ValueError("PGL round 1 differs from the seeded fixture")
        events = mk.poly_events(client)
        pm = {k[1]: v for k, v in mk.poly_matches(events).items() if k[0] == 1}
        derivs = [d for d in mk.poly_derivatives(events) if not d["closed"]]
        open_fx = [f for f in fixtures if f.status != "end"]
        try:
            km = mk.kalshi_matches(client, open_fx)
        except httpx.HTTPError:
            km = {}
        tokens = [m["tokens"][0] for m in pm.values() if not m["closed"] and m["accepting"]]
        tokens += [t for d in derivs for t in d["tokens"]]
        books = mk.poly_books(client, tokens)
        k_markets, k_mult = mk.kalshi_s2(client)
        k_books = {}
        for m in k_markets:
            if m["status"] == "active":
                k_books[m["market"]] = mk.kalshi_book(client, m["market"])
        try:
            k_maps = mk.kalshi_bo3_markets(client)
            map_mult = mk.kalshi_series_multiplier(client, "KXCS2TOTALMAPS")
            if mk.kalshi_series_multiplier(client, "KXCS2SPREAD") != map_mult:
                raise ValueError("Total-maps and spread fee multipliers differ")
        except httpx.HTTPError:
            k_maps, map_mult = {}, k_mult
        for rows in k_maps.values():
            for m in rows:
                if m["status"] == "active":
                    k_books[m["market"]] = mk.kalshi_book(client, m["market"])

        locks, overrides, observations, match_rows = {}, {}, [], []
        live_probs, map_breaks, missing = {}, [], []
        for f in fixtures:
            a, b = by_name[f.a], by_name[f.b]
            info = pm.get(frozenset((f.a, f.b)))
            close = None
            if info and info.get("start") and (f.status == "end" or in_play(f)):
                c = closing_price(client, cache, info["slug"], info["tokens"][0], info["start"])
                if c is not None:
                    close = c if info["outcomes"][0] == f.a else 1 - c
            if f.status == "end":
                locks[frozenset((a.id, b.id))] = by_name[f.winner].id
                if close is not None:
                    observations.append((a.id, b.id, close, f.bo))
                match_rows.append({"key": f.key, "round": f.round, "a": f.a, "b": f.b, "status": "end",
                                   "winner": f.winner, "close_a": close})
                continue
            p_a, src = match_quote(f, info, books, km)
            if in_play(f):
                live_probs[f.key] = p_a
                if p_a is None:
                    if at_map_break(f):
                        map_breaks.append((f, a, b, close))
                        src = "remaining maps"
                    else:
                        missing.append(f.key)
            pre = close if in_play(f) else p_a
            if pre is not None:
                observations.append((a.id, b.id, pre, f.bo))
            if p_a is not None:
                lo, hi = sorted((a.id, b.id))
                overrides[f"{lo}-{hi}"] = p_a if a.id == lo else 1 - p_a
            match_rows.append({"key": f.key, "round": f.round, "a": f.a, "b": f.b, "status": f.status,
                               "score": list(f.score), "p_a": p_a, "source": src, "close_a": close})
        cache_path.write_text(json.dumps(cache, indent=1))
        if missing:
            hold = "Waiting for live series odds: " + ", ".join(missing)
            snap = {"at": at.isoformat(), "reason": reason, "feed_updated": updated.get(1), "matches": match_rows,
                    "pickem": None, "entry_hold": hold, "quotes": [], "signals": [], "new_entries": 0}
            append("snapshots.jsonl", [snap])
            (STATE / "latest.md").write_text(f"# Singapore live pricing\n\n{hold}\n", encoding="utf-8")
            print(json.dumps({"at": snap["at"], "reason": reason, "entry_hold": hold, "new_entries": 0}))
            return snap
        check_draw(teams, locks, {k: v for k, v in overrides.items()}, fixtures, ids)

        fair, samples = {}, {}
        break_probs = {f.key: {} for f, _, _, _ in map_breaks}
        for label, (scale, lam) in SCENARIOS.items():
            strengths = fit_strengths(teams, observations, scale, lam)
            conditional = dict(overrides)
            for f, a, b, close in map_breaks:
                map_win = bo3_to_map(close) if close is not None else p_map(strengths[a.id], strengths[b.id], S)
                series_win = remaining_bo3(f.score, map_win)
                break_probs[f.key][label] = series_win
                lo, hi = sorted((a.id, b.id))
                conditional[f"{lo}-{hi}"] = series_win if a.id == lo else 1 - series_win
            res = run_mc(teams, strengths, S, N_SIMS, locks, seed=SEED,
                         market_blend={k: (v, 0.0) for k, v in conditional.items()})
            fair[label], samples[label] = records(res.sample, ids)
        for row in match_rows:
            if row["key"] in break_probs:
                probs = break_probs[row["key"]]
                row.update(p_a=probs["base"], p_a_low=min(probs.values()), p_a_high=max(probs.values()))

        def band(team, family):
            vals = [fair[s][by_name[team].id][family] for s in SCENARIOS]
            return fair["base"][by_name[team].id][family], min(vals), max(vals)

        se = lambda p: math.sqrt(max(p * (1 - p), 1e-6) / N_SIMS)
        playing = {name for f in fixtures if in_play(f) for name in (f.a, f.b)}
        quotes, signals = [], []
        for d in derivs:
            p, lo, hi = band(d["team"], d["family"])
            yes, no = books.get(d["tokens"][0]), books.get(d["tokens"][1])
            row = {"venue": "polymarket", "family": d["family"], "team": d["team"], "market": d["market"],
                   "fair": round(p, 4), "fair_lo": round(lo, 4), "fair_hi": round(hi, 4),
                   "bid": yes["bids"][0][0] if yes and yes["bids"] else None,
                   "ask": yes["asks"][0][0] if yes and yes["asks"] else None, "volume": d["volume"],
                   "accepting": d["accepting"]}
            for side, book, worst in (("yes", yes, lo - 2 * se(lo)), ("no", no, 1 - hi - 2 * se(hi))):
                cost = taker_cost_poly(book, POLY_SHARES, d["fee_rate"])
                if cost:
                    row[f"{side}_unit"] = round(cost["unit"], 4)
                    edge = worst - cost["unit"]
                    row[f"{side}_edge"] = round(edge, 4)
                    if edge >= EDGE_MIN and d["accepting"]:
                        signals.append({"at": at.isoformat(), "reason": reason, "venue": "polymarket", "in_play": d["team"] in playing,
                                        "market": d["market"], "token": d["tokens"][0 if side == "yes" else 1],
                                        "family": d["family"], "team": d["team"], "side": side,
                                        "shares": POLY_SHARES, "avg": round(cost["avg"], 4),
                                        "unit_cost": round(cost["unit"], 4), "fair": round(p if side == "yes" else 1 - p, 4),
                                        "worst_fair": worst, "edge": round(edge, 4)})
            quotes.append(row)
        for m in k_markets:
            if m["market"] not in k_books:
                continue
            p, lo, hi = band(m["team"], "qualify")
            book = k_books[m["market"]]
            row = {"venue": "kalshi", "family": "qualify", "team": m["team"], "market": m["market"],
                   "fair": round(p, 4), "fair_lo": round(lo, 4), "fair_hi": round(hi, 4)}
            yb, nb = book.get("yes_dollars") or [], book.get("no_dollars") or []
            row["bid"] = max((float(x[0]) for x in yb), default=None)
            row["ask"] = round(1 - max((float(x[0]) for x in nb), default=1.0), 4) if nb else None
            for side, worst in (("yes", lo - 2 * se(lo)), ("no", 1 - hi - 2 * se(hi))):
                cost = kalshi_cost(book, side, k_mult)
                if cost:
                    unit = cost["unit"]
                    edge = worst - unit
                    row[f"{side}_unit"] = round(unit, 4)
                    row[f"{side}_edge"] = round(edge, 4)
                    if edge >= EDGE_MIN:
                        signals.append({"at": at.isoformat(), "reason": reason, "venue": "kalshi", "in_play": m["team"] in playing,
                                        "market": m["market"], "family": "qualify", "team": m["team"],
                                        "side": side, "shares": KALSHI_SIZE, "avg": round(cost["avg"], 4),
                                        "unit_cost": round(unit, 4), "fair": round(p if side == "yes" else 1 - p, 4),
                                        "worst_fair": worst, "edge": round(edge, 4)})
            quotes.append(row)

        # Exploratory: Kalshi best-of-three map-score markets, priced from the match price alone.
        map_rows = [m for rows in k_maps.values() for m in rows]
        for f in fixtures:
            bound = fixture_map_markets(f, k_maps, km) if f.bo == 3 and f.status != "end" else []
            if not bound:
                continue
            mr = next(m for m in match_rows if m["key"] == f.key)
            if mr.get("p_a") is None:
                continue
            # Fresh maps need the pre-match strength. Mid-match, the live price is not a substitute.
            pre = mr.get("close_a") if mr.get("close_a") is not None else (None if in_play(f) else mr["p_a"])
            if pre is None:
                continue
            probs = map_score_probs(mr["p_a"], bo3_to_map(pre), f.score)
            for m in bound:
                if m["market"] not in k_books:
                    continue
                p = probs["over"] if m["kind"] == "over" else probs["sweep_a"] if m["team"] == f.a else probs["sweep_b"]
                book = k_books[m["market"]]
                yb, nb = book.get("yes_dollars") or [], book.get("no_dollars") or []
                row = {"venue": "kalshi", "family": "maps", "team": m["team"] or "over 2.5", "market": m["market"],
                       "match": f"{f.a} vs {f.b}", "score": list(f.score), "fair": round(p, 4), "fair_lo": round(p, 4),
                       "fair_hi": round(p, 4), "bid": max((float(x[0]) for x in yb), default=None),
                       "ask": round(1 - max((float(x[0]) for x in nb), default=1.0), 4) if nb else None}
                for side, fair_side in (("yes", p), ("no", 1 - p)):
                    cost = kalshi_cost(book, side, map_mult)
                    if cost:
                        row[f"{side}_unit"] = round(cost["unit"], 4)
                        row[f"{side}_edge"] = round(fair_side - cost["unit"], 4)
                        if fair_side - cost["unit"] >= EDGE_MIN_MAPS:
                            signals.append({"at": at.isoformat(), "reason": reason, "venue": "kalshi",
                                            "in_play": f.a in playing, "market": m["market"], "family": "maps",
                                            "kind": m["kind"], "team": m["team"], "label": m["label"],
                                            "match_key": f.key, "a": f.a, "b": f.b, "score": list(f.score),
                                            "side": side, "shares": KALSHI_SIZE, "avg": round(cost["avg"], 4),
                                            "unit_cost": round(cost["unit"], 4), "fair": round(fair_side, 4),
                                            "worst_fair": fair_side, "edge": round(fair_side - cost["unit"], 4)})
                quotes.append(row)

        # Only venues the user can trade produce paper entries; the rest stay in the snapshot as reference.
        reference = [s for s in signals if s["venue"] not in PAPER_VENUES]
        signals = [s for s in signals if s["venue"] in PAPER_VENUES]
        terms = {(m["venue"], m["market"]): m for m in [*derivs, *k_markets, *map_rows]}
        signals, hold = confirm_signals(client, signals, fx, live_probs, terms)

    # Pick'Em: chance the locked card still reaches five correct.
    card = json.loads(CARD.read_text())["card"]
    arr = samples["base"]
    pos = {i: k for k, i in enumerate(ids)}
    hits = np.zeros(arr.shape[0], dtype=np.int8)
    for t in card["3-0"]:
        k = pos[by_name[t].id]; hits += (arr[:, k, 0] == 3) & (arr[:, k, 1] == 0)
    for t in card["3-1 or 3-2"]:
        k = pos[by_name[t].id]; hits += (arr[:, k, 0] == 3) & (arr[:, k, 1] >= 1)
    for t in card["0-3"]:
        k = pos[by_name[t].id]; hits += (arr[:, k, 0] == 0) & (arr[:, k, 1] == 3)
    pickem = {"p_ge5": float(np.mean(hits >= 5)), "expected": float(hits.mean()),
              "max_possible": int(hits.max())}

    # Freeze the first entry per market side.
    entries_path = STATE / "entries.jsonl"
    seen = {(e["venue"], e["market"], e["side"]) for e in map(json.loads, entries_path.read_text().splitlines())} if entries_path.exists() else set()
    new = [s for s in signals if (s["venue"], s["market"], s["side"]) not in seen]
    append("entries.jsonl", new)
    snap = {"at": at.isoformat(), "reason": reason, "feed_updated": updated.get(1), "matches": match_rows,
            "locks": len(locks), "priced_matches": len(overrides), "observations": len(observations),
            "pickem": pickem, "quotes": quotes, "signals": signals, "reference_signals": reference,
            "new_entries": len(new), "entry_hold": hold}
    append("snapshots.jsonl", [snap])
    write_latest(snap)
    summary = {"at": snap["at"], "reason": reason, "pickem_p_ge5": round(pickem["p_ge5"], 4),
               "entry_hold": hold,
               "live_teams": sorted(playing), "new_in_play": sum(bool(s.get("in_play")) for s in new),
               "pickem_max": pickem["max_possible"], "signals": len(signals), "new_entries": len(new),
               "new": [" ".join(x for x in (s["family"], s.get("team") or "", s.get("kind", ""), s["side"].upper(),
                                            f"@{s['unit_cost']:.2f} fair {s['fair']:.2f}", "in-play" if s.get("in_play") else "") if x)
                       for s in new],
               "top": [f"{s['venue']} {s['family']} {s.get('team') or s.get('kind', '')} {s['side'].upper()} @{s['unit_cost']:.3f} fair>={s['worst_fair']:.3f} edge {100*s['edge']:.1f}c{' in-play' if s.get('in_play') else ''}"
                       for s in sorted(signals, key=lambda s: -s["edge"])[:5]]}
    if not quiet:
        print((STATE / "latest.md").read_text())
    print(json.dumps(summary))
    return snap


def write_latest(snap):
    lines = [f"# Singapore live pricing · {snap['at'][:19]}Z · {snap['reason']}", "",
             f"Pick'Em card: P(5+ correct) {snap['pickem']['p_ge5']:.1%}, expected {snap['pickem']['expected']:.2f}, best case {snap['pickem']['max_possible']}/10", "",
             "| Match | Status | Price (first team) | Source |", "|---|---|---|---|"]
    for m in snap["matches"]:
        if m["status"] != "end":
            price = f"{m['p_a']:.3f}" if m.get("p_a") is not None else "n/a"
            if "p_a_low" in m:
                price += f" ({m['p_a_low']:.3f}-{m['p_a_high']:.3f})"
            lines.append(f"| {m['a']} vs {m['b']} | {m['status']} {m.get('score', '')} | {price} | {m.get('source')} |")
    lines += ["", "| Venue | Market | Team | Fair (range) | Bid / Ask | YES edge | NO edge |", "|---|---|---|---|---|---|---|"]
    rows = sorted(snap["quotes"], key=lambda q: -max(q.get("yes_edge", -1), q.get("no_edge", -1)))
    for q in rows[:40]:
        lines.append(f"| {q['venue']} | {q['family']} | {q['team']} | {q['fair']:.3f} ({q['fair_lo']:.3f}-{q['fair_hi']:.3f}) | "
                     f"{q.get('bid')} / {q.get('ask')} | {q.get('yes_edge', '')} | {q.get('no_edge', '')} |")
    lines += ["", f"Signals this snapshot: {len(snap['signals'])}, new paper entries: {snap['new_entries']}. "
              "Edges are after taker fees against the least favorable scenario. Paper only."]
    if snap.get("entry_hold"):
        lines.append(snap["entry_hold"])
    (STATE / "latest.md").write_text("\n".join(lines) + "\n")


def grade() -> dict:
    """Settle frozen entries once Stage 1 records are final on PGL."""
    STATE.mkdir(exist_ok=True)
    with httpx.Client(timeout=25) as client:
        fx, _ = feed.fetch(client, (1,))
    rec = {}
    for f in fx.values():
        if f.status != "end":
            continue
        for team, won in ((f.a, f.winner == f.a), (f.b, f.winner == f.b)):
            w, l = rec.get(team, (0, 0))
            rec[team] = (w + won, l + (not won))
    final = {t: r for t, r in rec.items() if r[0] == 3 or r[1] == 3}
    path = STATE / "entries.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    settled = []
    for e in rows:
        if e["family"] == "maps":
            f = fx.get(e["match_key"])
            if not f or f.status != "end" or {f.a, f.b} != {e["a"], e["b"]}:
                continue
            a_maps, b_maps = f.score if f.a == e["a"] else f.score[::-1]
            if e["kind"] == "over":
                hit = a_maps + b_maps == 3
            else:
                hit = (a_maps, b_maps) == (2, 0) if e["team"] == e["a"] else (a_maps, b_maps) == (0, 2)
            payoff = float(hit if e["side"] == "yes" else not hit)
            settled.append({**e, "final_maps": [a_maps, b_maps], "payoff": payoff,
                            "pnl": round(e["shares"] * (payoff - e["unit_cost"]), 4)})
            continue
        if e["team"] not in final:
            continue
        hit = final[e["team"]] in RECORDS[e["family"]]
        payoff = float(hit if e["side"] == "yes" else not hit)
        settled.append({**e, "record": final[e["team"]], "payoff": payoff,
                        "pnl": round(e["shares"] * (payoff - e["unit_cost"]), 4)})
    out = {"entries": len(rows), "settled": len(settled),
           "pnl_usd": round(sum(s["pnl"] for s in settled), 2),
           "staked_usd": round(sum(s["shares"] * s["unit_cost"] for s in settled), 2), "rows": settled}
    # Pre-registered split (Nov 24, before round 3): Kalshi qualify entries made in-play are the
    # hypothesis and the other Kalshi qualify entries the control. Map-score markets are exploratory;
    # Polymarket entries (logged before the Kalshi-only decision) are reference only.
    groups = {
        "hypothesis_kalshi_qualify_in_play": lambda s: s["venue"] == "kalshi" and s["family"] == "qualify" and s.get("in_play"),
        "control_kalshi_qualify_not_in_play": lambda s: s["venue"] == "kalshi" and s["family"] == "qualify" and not s.get("in_play"),
        "exploratory_kalshi_maps": lambda s: s["venue"] == "kalshi" and s["family"] == "maps",
        "reference_polymarket": lambda s: s["venue"] != "kalshi",
    }
    for label, keep in groups.items():
        part = [s for s in settled if keep(s)]
        per_share = [s["pnl"] / s["shares"] for s in part]
        out[label] = {"settled": len(part), "pnl_usd": round(sum(s["pnl"] for s in part), 2),
                      "mean_per_share": round(float(np.mean(per_share)), 4) if part else None,
                      "se_per_share": round(float(np.std(per_share, ddof=1) / math.sqrt(len(part))), 4) if len(part) > 1 else None}
    (STATE / "graded.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reason", default="manual")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--grade", action="store_true")
    args = ap.parse_args(argv)
    if args.grade:
        grade()
    else:
        snapshot(args.reason, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
