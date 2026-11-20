"""Fit the first Singapore Pick'Em, then score that fixed card on fresh tournaments."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from engine.montecarlo import run_mc, wilson
from engine.optimizer import (
    COIN_THRESHOLD, Ballot, ballot_a, ballot_b, build_outcome_matrices, correct_counts,
    e_correct, marginals_from_matrices, p_ge5, single_replacements,
)
from engine.teams import build_round1_pairs, load_stage

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/singapore2026/stage1.json"
FORECAST = ROOT / "data/singapore2026/forecast.json"
SPREAD = 60.0  # 600 raw VRS points per tenfold change in map win odds
SEED = 20261121


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


BUCKETS = (("3-0", "picks_30"), ("3-1 or 3-2", "picks_adv"), ("0-3", "picks_03"))
OLD_CARD = (("100 Thieves", "PVISION"), ("HEROIC", "Liquid", "NIP", "FaZe", "Eternal Fire", "DENDELE"),
            ("Chinggis Warriors", "Lynn Vision"))
CARRIES = {"Opener only": 0, "Half carry": 0.5, "Full carry": 1}


def paired(matrices, first, second):
    passes = correct_counts(first, matrices) >= COIN_THRESHOLD
    other = correct_counts(second, matrices) >= COIN_THRESHOLD
    a, b = int(np.sum(passes & ~other)), int(np.sum(other & ~passes))
    n = len(passes)
    delta = (a - b) / n
    half = 1.96 * math.sqrt(max(0.0, (a + b) / n - delta**2) / n)
    return dict(p_ge5=float(other.mean()), card_only=a, alternative_only=b, n=n,
                card_minus_alternative=delta, ci95_delta=[delta - half, delta + half])


def model_inputs(teams, openers, model, form):
    if model == "Ratings only":
        return None, None
    ratings, prices = market_inputs(teams, openers, CARRIES.get(model, 0))
    if model == "Recent maps":
        ratings = {t.id: form[t.name] for t in teams}
    elif model not in CARRIES:
        raise ValueError(f"Unknown strength model {model}")
    return ratings, prices


def forecast(n_select=100_000, n_evaluate=200_000, n_sensitivity=25_000, seed=SEED, *, refresh_openers=False):
    teams, _ = load_stage(FIXTURE)
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    audit = json.loads((FIXTURE.parent / "evidence/validation.json").read_text(encoding="utf-8"))
    if refresh_openers:
        from odds.singapore_openers import refresh

        data["openers"], data["quotes_observed_at"] = refresh(data)
    ids = [t.id for t in teams]
    names = {t.id: t.name for t in teams}
    name_ids = {t.name: t.id for t in teams}
    model = audit["chosen"]
    form = audit["singapore_form"]
    ratings, prices = model_inputs(teams, data["openers"], model, form)
    selection = run_mc(teams, ratings, SPREAD, n_select, seed=seed, market_blend=prices)
    matrices = build_outcome_matrices(selection.sample, ids)
    del selection
    card = ballot_b(ballot_a(*marginals_from_matrices(matrices)), matrices, ids)
    alternate_card = max(single_replacements(card, ids), key=lambda c: p_ge5(c, matrices))
    bucket = next(label for label, f in BUCKETS if getattr(card, f) != getattr(alternate_card, f))
    replaced, = set(card.all_ids) - set(alternate_card.all_ids)
    reserve, = set(alternate_card.all_ids) - set(card.all_ids)
    old_card = Ballot(*(tuple(name_ids[name] for name in group) for group in OLD_CARD))
    del matrices

    held_out = run_mc(teams, ratings, SPREAD, n_evaluate, seed=seed + 1, market_blend=prices)
    matrices = build_outcome_matrices(held_out.sample, ids)
    evaluation = score(matrices, card, held_out.n)
    swap = {"out": names[replaced], "bucket": bucket, "in": names[reserve], **paired(matrices, card, alternate_card)}
    prior = paired(matrices, card, old_card)
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
    for label in ["Ratings only", *CARRIES, "Recent maps"]:
        if label == model:
            continue
        alternate, overrides = model_inputs(teams, data["openers"], label, form)
        sample = run_mc(teams, alternate, SPREAD, n_sensitivity, seed=seed + 2, market_blend=overrides)
        sensitivity[label] = score(build_outcome_matrices(sample.sample, ids), card, sample.n)
        del sample

    line_tests = []
    for change in (0.05, 0.10):
        openers = [dict(row) for row in data["openers"]]
        row = next(q for q in openers if names[reserve] in q["teams"])
        reserve_first = row["teams"][0] == names[reserve]
        midpoint = (row["bid"] + row["ask"]) / 2
        direction = -1 if bucket == "0-3" else 1
        changed = np.clip(midpoint + direction * (1 if reserve_first else -1) * change, 0.001, 0.999)
        row.update(bid=changed, ask=changed)
        alt, overrides = model_inputs(teams, openers, model, form)
        sample = run_mc(teams, alt, SPREAD, n_sensitivity, seed=seed + 3, market_blend=overrides)
        result = paired(build_outcome_matrices(sample.sample, ids), card, alternate_card)
        line_tests.append(dict(team=names[reserve], opponent=next(n for n in row["teams"] if n != names[reserve]),
                               current=midpoint if reserve_first else 1-midpoint,
                               tested=float(changed if reserve_first else 1-changed), **result))
        del sample
    return {
        "event": data["event"], "stage": 1, "starts_at": data["starts_at"],
        "quotes_observed_at": data["quotes_observed_at"], "seed": seed, "n_select": n_select,
        **({"updated_openers": data["openers"]} if refresh_openers else {}),
        "card": {label: [names[i] for i in getattr(card, field)] for label, field in BUCKETS},
        "model": model, "evaluation": evaluation, "teams": rows, "sensitivity": sensitivity,
        "closest_swap": swap, "previous_card": prior, "line_tests": line_tests,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select", type=int, default=100_000)
    parser.add_argument("--evaluate", type=int, default=200_000)
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
