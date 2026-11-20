"""Fit the first Singapore Pick'Em, then score that fixed card on fresh tournaments."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from engine.montecarlo import run_mc, wilson
from engine.optimizer import Ballot, build_outcome_matrices, e_correct, marginals_from_matrices, optimize, p_ge5
from engine.teams import build_round1_pairs, load_stage

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/singapore2026/stage1.json"
FORECAST = ROOT / "data/singapore2026/forecast.json"
SPREAD = 60.0  # 600 raw VRS points per tenfold change in map win odds
SEED = 20261119


def market_inputs(teams, openers, carry):
    """Keep each pair's mean rating and carry a fraction of its market log-odds gap forward."""
    pairs = {(a.name, b.name): (a, b) for a, b in build_round1_pairs(teams)}
    if len(openers) != len(pairs) or {tuple(row["teams"]) for row in openers} != set(pairs):
        raise ValueError("Market snapshot must cover the eight seeded opening pairs in order of side")
    ratings = {t.id: t.rating for t in teams}
    prices = {}
    for row in openers:
        a, b = pairs[tuple(row["teams"])]
        if not 0 < row["bid"] <= row["ask"] < 1:
            raise ValueError(f"Invalid two-sided quote for {a.name} vs {b.name}")
        p = (row["bid"] + row["ask"]) / 2
        prices[f"{a.id}-{b.id}"] = (p, 0.0)
        market_gap = SPREAD * math.log10(p / (1 - p))
        shift = carry * (market_gap - (a.rating - b.rating)) / 2
        ratings[a.id] += shift
        ratings[b.id] -= shift
    return ratings, prices


def score(matrices, card, n):
    prob = p_ge5(card, matrices)
    return {
        "n": n, "p_ge5": prob,
        "ci95_sampling": wilson(round(prob * n), n),
        "expected_correct": e_correct(card, *marginals_from_matrices(matrices)),
    }


def forecast(n_select=100_000, n_evaluate=100_000, n_sensitivity=25_000, seed=SEED, *, refresh_openers=False):
    teams, _ = load_stage(FIXTURE)
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if refresh_openers:
        from odds.singapore_openers import refresh

        data["openers"], data["quotes_observed_at"] = refresh(data)
    ids = [t.id for t in teams]
    names = {t.id: t.name for t in teams}
    ratings, prices = market_inputs(teams, data["openers"], carry=0.5)
    selection = run_mc(teams, ratings, SPREAD, n_select, seed=seed, market_blend=prices)
    card = optimize(selection, teams).recommended
    # Preselect the alternate from the training sample as well, before looking at evaluation.
    middle_hits = {i: selection.counts_advance[i] - selection.counts_30[i] for i in ids}
    weakest = min(card.picks_adv, key=middle_hits.get)
    reserve = max((i for i in ids if i not in card.all_ids), key=middle_hits.get)
    replacement = tuple(reserve if i == weakest else i for i in card.picks_adv)
    alternate_card = Ballot(card.picks_30, replacement, card.picks_03)
    del selection

    held_out = run_mc(teams, ratings, SPREAD, n_evaluate, seed=seed + 1, market_blend=prices)
    matrices = build_outcome_matrices(held_out.sample, ids)
    evaluation = score(matrices, card, held_out.n)
    swap = {"out": names[weakest], "in": names[reserve], "p_ge5": p_ge5(alternate_card, matrices)}
    del matrices
    rows = []
    for t in teams:
        sweep = held_out.counts_30[t.id]
        qualify = held_out.counts_advance[t.id]
        rows.append(dict(seed=t.seed, team=t.name, sweep=sweep / held_out.n,
                         advance_pick=(qualify - sweep) / held_out.n, qualify=qualify / held_out.n,
                         winless=held_out.counts_03[t.id] / held_out.n))
    del held_out

    sensitivity = {}
    for label, carry in (("VRS only", None), ("Market in round one only", 0.0),
                         ("Full market adjustment", 1.0)):
        alternate, overrides = (None, None) if carry is None else market_inputs(teams, data["openers"], carry)
        sample = run_mc(teams, alternate, SPREAD, n_sensitivity, seed=seed + 2, market_blend=overrides)
        sensitivity[label] = score(build_outcome_matrices(sample.sample, ids), card, sample.n)
        del sample
    return {
        "event": data["event"], "stage": 1, "starts_at": data["starts_at"],
        "quotes_observed_at": data["quotes_observed_at"], "seed": seed, "n_select": n_select,
        **({"updated_openers": data["openers"]} if refresh_openers else {}),
        "card": {label: [names[i] for i in picked] for label, picked in
                 (("3-0", card.picks_30), ("3-1 or 3-2", card.picks_adv), ("0-3", card.picks_03))},
        "evaluation": evaluation, "teams": rows, "sensitivity": sensitivity, "advance_swap": swap,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select", type=int, default=100_000)
    parser.add_argument("--evaluate", type=int, default=100_000)
    parser.add_argument("--sensitivity", type=int, default=25_000, help="tournaments per alternate model")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--refresh-openers", action="store_true", help="fetch eight current pre-match prices")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if min(args.select, args.evaluate, args.sensitivity) < 1 or args.seed < 0:
        parser.error("sample sizes must be positive and seed must be nonnegative")
    destination = args.output or (ROOT / "data/_singapore_stage1_latest.json" if args.refresh_openers else FORECAST)
    result = forecast(args.select, args.evaluate, args.sensitivity, args.seed, refresh_openers=args.refresh_openers)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if destination.resolve() == FORECAST:
        from ui.singapore_report import render, static_page

        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        (ROOT / "public/index.html").write_text(static_page(render(result, fixture)), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("card", "evaluation", "sensitivity")}, indent=2))


if __name__ == "__main__":
    main()
