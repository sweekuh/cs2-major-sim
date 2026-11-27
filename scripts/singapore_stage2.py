"""Singapore Stage 2: re-check the Stage 1 model on Stage 1's results, then fit and score the Stage 2 Pick'Em.

Run from the repo root:  uv run --frozen python -m scripts.singapore_stage2 [--refresh-openers]
Writes data/singapore2026/evidence/stage2-validation.json and data/singapore2026/forecast_stage2.json.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from engine.montecarlo import run_mc
from engine.optimizer import (
    ballot_a, ballot_b, build_outcome_matrices, marginals_from_matrices, p_ge5, single_replacements,
)
from engine.probs import series_prob
from engine.teams import Team, build_round1_pairs, load_stage
from odds.base import devig_fixed_two_way
from scripts.singapore_stage1 import BUCKETS, CARRIES, SPREAD, SPREAD_GRID, mixture, model_inputs, paired, score
from scripts.validate_singapore import EVIDENCE, metrics, replay, spread_weights

ROOT = Path(__file__).resolve().parents[1]
STAGE1 = ROOT / "data/singapore2026/stage1.json"
FIXTURE = ROOT / "data/singapore2026/stage2.json"
RESULTS1 = EVIDENCE / "singapore-stage1-results.json"
FORECAST = ROOT / "data/singapore2026/forecast_stage2.json"
REVALIDATION = EVIDENCE / "stage2-validation.json"
SEED = 20261128
# The map-form challenger needs a Stage 2 map archive that was not assembled; it also scored worst
# on all three historical events, so the comparison keeps the rating and market models only.
MODELS = ["Ratings only", *CARRIES]
# Venue spellings that differ from the fixture names.
ALIASES = {
    "FUT ESPORTS": "FUT Esports", "FUT": "FUT Esports", "Nemiga Gaming": "Nemiga", "G2 Esports": "G2",
    "THE ONE": "The One", "the ONE": "The One", "TheMongolz": "The MongolZ", "The Mongolz": "The MongolZ",
    "Ninjas in Pyjamas": "NIP", "PARIVISION": "PVISION", "Team Liquid": "Liquid", "NAVI": "Natus Vincere",
}


def events():
    """The three historical Stage 1s plus Singapore Stage 1, each as (label, teams, by_name, openers, matches)."""
    out = []
    for label, stage in json.loads((EVIDENCE / "historical-stages.json").read_text(encoding="utf-8")).items():
        teams = [Team(t["seed"], t["name"], t["seed"], t["vrs"] / 10) for t in stage["teams"]]
        by_name = {t.name: t for t in teams}
        openers = []
        for q in stage["openers"]:
            a, b = sorted(q["teams"], key=lambda n: by_name[n].seed)
            prob = devig_fixed_two_way(*q["decimal"]) if "decimal" in q else (q["bid"] + q["ask"]) / 2
            p = prob if a == q["teams"][0] else 1 - prob
            openers.append(dict(teams=[a, b], bid=p, ask=p))
        out.append((label, teams, by_name, openers, stage["matches"]))
    # Singapore Stage 1 exactly as forecast: November 19 ratings and the frozen Polymarket openers.
    teams, _ = load_stage(STAGE1)
    by_name = {t.name: t for t in teams}
    frozen = json.loads(STAGE1.read_text(encoding="utf-8"))["openers"]
    openers = [dict(teams=q["teams"], bid=(q["bid"] + q["ask"]) / 2, ask=(q["bid"] + q["ask"]) / 2) for q in frozen]
    matches = json.loads(RESULTS1.read_text(encoding="utf-8"))["matches"]
    out.append(("singapore", teams, by_name, openers, matches))
    return out


def later_round_scores(teams, by_name, openers, matches, model, spread=SPREAD):
    ratings, _ = model_inputs(teams, openers, model, {}, spread)
    ratings = ratings or {t.id: t.rating for t in teams}
    probs = []
    for m in matches:
        if m["round"] == 1:
            continue
        a, b = sorted([by_name[n] for n in m["teams"]], key=lambda t: t.seed)
        p = series_prob(ra=ratings[a.id], rb=ratings[b.id], bo3=m["bo"] == 3, S=spread)
        probs.append(p if a.name == m["winner"] else 1 - p)
    return probs


def revalidate(model="Full carry"):
    evs = events()
    singapore = next(e for e in evs if e[0] == "singapore")
    replayed = replay(singapore[1], singapore[4])  # the engine must reproduce PGL's Stage 1 draw
    scores = {label: {m: metrics(later_round_scores(t, bn, o, ms, m)) for m in MODELS} for label, t, bn, o, ms in evs}
    by_spread = {}
    for spread in SPREAD_GRID:
        loss = -sum(math.log(p) for p in later_round_scores(*singapore[1:], model, spread))
        by_spread[str(round(spread * 10))] = round(loss, 4)
    prepared = lambda keep: [(t, bn, o, ms, {}) for label, t, bn, o, ms in evs if keep(label)]
    return dict(
        model=model,
        singapore_replayed=replayed,
        later_round_scores=scores,
        singapore_later_log_loss_sum_by_spread=by_spread,
        spread_weights_historical=spread_weights(prepared(lambda l: l != "singapore"), model),
        spread_weights=spread_weights(prepared(lambda l: True), model),
    )


def venue_name(name):
    from analysis.singapore_live.names import canon

    raw = canon(name, strict=False)
    return ALIASES.get(raw, ALIASES.get(name, raw))


def refresh_openers(data):
    """Current Polymarket bid and ask for the eight opening matches, oriented to the higher seed."""
    import httpx

    from analysis.singapore_live import markets as mk

    if datetime.now(timezone.utc) >= datetime.fromisoformat(data["starts_at"].replace("Z", "+00:00")):
        raise ValueError("Stage 2 has started. Use the frozen pre-match quotes for a replay.")
    with httpx.Client(timeout=25) as client:
        events_ = mk.poly_events(client)
        listed = {}
        for e in events_:
            if "PGL Major Singapore Stage 2" not in e.get("title", ""):
                continue
            for m in e["markets"]:
                if m.get("sportsMarketType") == "moneyline" and m.get("slug") == e["slug"]:
                    outcomes = [venue_name(x) for x in json.loads(m["outcomes"])]
                    listed[frozenset(outcomes)] = (e["slug"], outcomes, json.loads(m["clobTokenIds"]))
        books = mk.poly_books(client, [v[2][0] for v in listed.values()])
    quotes = []
    for q in data["openers"]:
        slug, outcomes, tokens = listed[frozenset(q["teams"])]
        book = books[tokens[0]]
        bid, ask = book["bids"][0][0], book["asks"][0][0]
        if outcomes[0] != q["teams"][0]:
            bid, ask = 1 - ask, 1 - bid
        quotes.append(dict(teams=q["teams"], bid=round(bid, 4), ask=round(ask, 4), slug=slug))
    return quotes, datetime.now(timezone.utc).isoformat(timespec="seconds")


def market_check(rows):
    """Model qualification odds next to Kalshi and Polymarket "reach Stage 3" prices (read only)."""
    import httpx

    from analysis.singapore_live import markets as mk

    out = {r["team"]: {"model": r["qualify"]} for r in rows}
    with httpx.Client(timeout=25) as client:
        kalshi = client.get("https://api.elections.kalshi.com/trade-api/v2/events/KXCS2QUALIFIERS-26PGLSGS3",
                            params={"with_nested_markets": "true"}).json()
        for m in kalshi.get("event", {}).get("markets", []) or kalshi.get("markets", []):
            team = venue_name(m.get("yes_sub_title") or "")
            if team in out:
                bid, ask = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 1)
                out[team]["kalshi"] = dict(bid=bid, ask=ask, ticker=m["ticker"])
        poly = next((e for e in mk.poly_events(client) if e.get("title") == "PGL Major Singapore 2026: Qualify to Stage 3"), None)
        if poly:
            tokens = {}
            for m in poly["markets"]:
                team = venue_name(m.get("groupItemTitle") or "")
                if team in out and not m.get("closed"):
                    tokens[team] = json.loads(m["clobTokenIds"])[0]
            books = mk.poly_books(client, list(tokens.values()))
            for team, token in tokens.items():
                b = books.get(token) or {}
                if b.get("bids") and b.get("asks"):
                    out[team]["polymarket"] = dict(bid=b["bids"][0][0], ask=b["asks"][0][0])
    # Venues can disagree by tens of points (Kalshi Astralis 16-19 cents against Polymarket 47-50 on
    # November 27), so each venue is compared on its own, and only where its book is 10 cents wide or less.
    for row in out.values():
        for venue in ("kalshi", "polymarket"):
            quote = row.get(venue)
            if quote and quote["ask"] - quote["bid"] <= 0.10:
                quote["mid"] = round((quote["bid"] + quote["ask"]) / 2, 4)
                row[f"model_minus_{venue}"] = round(row["model"] - quote["mid"], 4)
    return dict(observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), teams=out)


def cross_check(cards, weights, n, seed, data):
    """P(>=5) of fixed cards (name lists by bucket) under every model, on shared fresh tournaments per model."""
    from engine.optimizer import Ballot

    teams, _ = load_stage(FIXTURE)
    ids = {t.name: t.id for t in teams}
    ballots = {label: Ballot(*(tuple(ids[n] for n in card[bucket]) for bucket, _ in BUCKETS)) for label, card in cards.items()}
    out = {}
    for k, model in enumerate(MODELS):
        matrices = mixture(teams, data["openers"], model, {}, weights, n, seed + 100 * k)
        out[model] = {label: score(matrices, ballot, n) for label, ballot in ballots.items()}
        if len(ballots) == 2:
            first, second = ballots.values()
            out[model]["paired"] = paired(matrices, first, second)
        del matrices
    return out


def forecast(weights, model, n_select, n_evaluate, n_sensitivity, seed, data):
    teams, _ = load_stage(FIXTURE)
    openers = data["openers"]
    ids = [t.id for t in teams]
    names = {t.id: t.name for t in teams}
    matrices = mixture(teams, openers, model, {}, weights, n_select, seed)
    card = ballot_b(ballot_a(*marginals_from_matrices(matrices)), matrices, ids)
    alternate_card = max(single_replacements(card, ids), key=lambda c: p_ge5(c, matrices))
    bucket = next(label for label, f in BUCKETS if getattr(card, f) != getattr(alternate_card, f))
    replaced, = set(card.all_ids) - set(alternate_card.all_ids)
    reserve, = set(alternate_card.all_ids) - set(card.all_ids)
    del matrices

    matrices = mixture(teams, openers, model, {}, weights, n_evaluate, seed + 1)
    evaluation = score(matrices, card, n_evaluate)
    swap = {"out": names[replaced], "bucket": bucket, "in": names[reserve], **paired(matrices, card, alternate_card)}
    sweep, advance, winless = marginals_from_matrices(matrices)
    rows = [dict(seed=t.seed, team=t.name, sweep=sweep[t.id], advance_pick=advance[t.id],
                 qualify=sweep[t.id] + advance[t.id], winless=winless[t.id]) for t in teams]
    del matrices

    by_spread = {}
    for spread in SPREAD_GRID:
        ratings, prices = model_inputs(teams, openers, model, {}, spread)
        sample = run_mc(teams, ratings, spread, n_sensitivity, seed=seed + 4, market_blend=prices)
        by_spread[str(round(spread * 10))] = {
            **score(build_outcome_matrices(sample.sample, ids), card, sample.n), "weight": weights[spread]}
        del sample

    sensitivity = {label: score(mixture(teams, openers, label, {}, weights, n_sensitivity, seed + 2), card, n_sensitivity)
                   for label in MODELS if label != model}

    line_tests = []
    for change in (0.05, 0.10):
        moved = [dict(row) for row in openers]
        row = next(q for q in moved if names[reserve] in q["teams"])
        reserve_first = row["teams"][0] == names[reserve]
        midpoint = (row["bid"] + row["ask"]) / 2
        direction = -1 if bucket == "0-3" else 1
        changed = float(np.clip(midpoint + direction * (1 if reserve_first else -1) * change, 0.001, 0.999))
        row.update(bid=changed, ask=changed)
        result = paired(mixture(teams, moved, model, {}, weights, n_sensitivity, seed + 3), card, alternate_card)
        line_tests.append(dict(team=names[reserve], opponent=next(n for n in row["teams"] if n != names[reserve]),
                               current=midpoint if reserve_first else 1 - midpoint,
                               tested=changed if reserve_first else 1 - changed, **result))
    return {
        "event": data["event"], "stage": 2, "starts_at": data["starts_at"],
        "quotes_observed_at": data["quotes_observed_at"], "openers": openers, "seed": seed, "n_select": n_select,
        "card": {label: [names[i] for i in getattr(card, field)] for label, field in BUCKETS},
        "model": model, "evaluation": evaluation, "by_spread": by_spread, "teams": rows,
        "sensitivity": sensitivity, "closest_swap": swap, "line_tests": line_tests,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--select", type=int, default=100_000)
    parser.add_argument("--evaluate", type=int, default=200_000)
    parser.add_argument("--sensitivity", type=int, default=25_000)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--refresh-openers", action="store_true", help="fetch current prices for the eight openers")
    parser.add_argument("--no-markets", action="store_true", help="skip the read-only market comparison")
    parser.add_argument("--model", choices=MODELS, help="override the validated model (alternative card)")
    parser.add_argument("--output", type=Path, default=FORECAST)
    args = parser.parse_args()
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    teams, _ = load_stage(FIXTURE)
    pairs = [(a.name, b.name) for a, b in build_round1_pairs(teams)]
    if [tuple(q["teams"]) for q in data["openers"]] != pairs:
        raise ValueError(f"Openers must follow the seeded round-1 pairs: {pairs}")
    if args.refresh_openers:
        data["openers"], data["quotes_observed_at"] = refresh_openers(data)
        FIXTURE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    audit = revalidate()
    REVALIDATION.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    weights = {float(s) / 10: w for s, w in audit["spread_weights"].items()}
    result = forecast(weights, args.model or audit["model"], args.select, args.evaluate, args.sensitivity, args.seed, data)
    if not args.no_markets:
        try:
            result["markets"] = market_check(result["teams"])
        except Exception as exc:  # the comparison is read only and must not block the forecast
            result["markets"] = {"error": repr(exc)}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("card", "evaluation", "sensitivity", "closest_swap")}, indent=2))


if __name__ == "__main__":
    main()
