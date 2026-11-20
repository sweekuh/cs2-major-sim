"""Pre-match model and executable ten-contract paper pricing for Singapore."""

import json
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

import numpy as np

from engine.probs import p_map, series_best_of

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SIZE = 10
GRID = np.arange(200.0, 5001.0, 10.0)
EVENTS = ["Austin 2025", "Budapest 2025", "Cologne 2026"]
D = Decimal


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fit():
    rows = read(HERE / "historical_series.json")["rows"]
    differences = np.array([r["ra"] - r["rb"] for r in rows])
    y = np.array([r["y"] for r in rows], dtype=bool)
    p = 1 / (1 + 10 ** (-differences[:, None] / GRID))
    p = np.where(np.array([r["bo3"] for r in rows])[:, None], p * p * (3 - 2 * p), p)
    loss = -np.log(np.where(y[:, None], p, 1 - p))
    brier = (p - y[:, None]) ** 2
    event = np.array([r["event"] for r in rows])
    stage = np.array([r["stage"] for r in rows])
    stage_losses = np.array(
        [loss[(event == e) & (stage == s)].mean(0) for e in EVENTS for s in (1, 2, 3)]
    )
    if len(rows) != 297 or any(
        sum((event == e) & (stage == s)) != 33 for e in EVENTS for s in (1, 2, 3)
    ):
        raise ValueError("Incomplete historical archive")
    # Resample whole Swiss stages to preserve dependence among opponents.
    weights = np.random.default_rng(20261120).multinomial(9, np.ones(9) / 9, size=5000)
    spreads = GRID[np.argmin(weights @ stage_losses, axis=1)]
    fitted = int(GRID[np.argmin(loss.mean(0))])
    walk = {}
    residuals = []
    hist = read(ROOT / "data/singapore2026/evidence/historical-stages.json")

    def scores(mask, column):
        return {
            "log_loss": float(loss[mask, column].mean()),
            "brier": float(brier[mask, column].mean()),
        }

    for i in (1, 2):
        train = np.isin(event, EVENTS[:i])
        test = event == EVENTS[i]
        index = int(loss[train].mean(0).argmin())

        walk[EVENTS[i]] = {
            "n": int(sum(test)),
            "spread": int(GRID[index]),
            "fit": scores(test, index),
            "repo600": scores(test, list(GRID).index(600)),
            "flat": {"log_loss": float(np.log(2)), "brier": 0.25},
        }
        archive = hist[EVENTS[i].split()[0].lower()]
        points = {t["name"]: t["vrs"] for t in archive["teams"]}
        for q in archive["openers"]:
            a, b = q["teams"]
            # Absolute market/model disagreement on map log odds. These archived openers were BO1s.
            log_odds = np.log(q["p"] / (1 - q["p"]))
            residuals.append(abs(log_odds - np.log(10) * (points[a] - points[b]) / GRID[index]))
    return {
        "n": len(rows),
        "fitted": fitted,
        "spread90": list(map(float, np.quantile(spreads, [0.05, 0.95]))),
        "residual80": float(np.quantile(residuals, 0.8)),
        "residual_n": len(residuals),
        "walk": walk,
    }


ALIASES = {
    "nip": "Ninjas in Pyjamas",
    "pvision": "PARIVISION",
    "gosh": "BC.Game",
    "bc game": "BC.Game",
    "bc.game esports": "BC.Game",
    "navi": "Natus Vincere",
    "the one": "1win",
    "bb team": "BETBOOM",
    "betboom team": "BETBOOM",
    "faze clan": "FaZe",
    "team liquid": "Liquid",
    "imperial esports": "Imperial",
    "lynn vision gaming": "Lynn Vision",
    "9z globant": "9z",
    "eternal fire esports": "Eternal Fire",
    "dendele cs": "DENDELE",
    "team spirit": "Spirit",
    "team vitality": "Vitality",
    "team falcons": "Falcons",
    "aurora gaming": "Aurora",
    "g2 esports": "G2",
    "fut esports": "FUT",
    "nemiga gaming": "Nemiga",
    "the mongolz": "The MongolZ",
}
POINTS = read(HERE / "nov19.json")["points"]
EARLIER = read(HERE / "ratings.json")["teams"]
NAMES = {**{n.casefold(): n for n in POINTS}, **ALIASES}


def name(s):
    return NAMES.get(s.strip().casefold(), s.strip())


def forecast(a, b, bo, fit_data):
    best = fit_data["fitted"]
    main = series_best_of(p_map(POINTS[a], POINTS[b], best), bo)
    log_gaps = [
        np.log(10) * (pa - pb) / s
        for pa, pb in [(POINTS[a], POINTS[b]), (EARLIER[a]["points"], EARLIER[b]["points"])]
        for s in fit_data["spread90"]
    ]
    lo = min(log_gaps) - fit_data["residual80"]
    hi = max(log_gaps) + fit_data["residual80"]
    return {
        "p": main,
        "low": series_best_of(1 / (1 + np.exp(-lo)), bo),
        "high": series_best_of(1 / (1 + np.exp(-hi)), bo),
    }


def order_cost(fills, multiplier):
    """Conservative non-direct-member cent-aligned total debit; micro-dollar fee rounding per level."""
    gross = sum(price * qty for price, qty in fills)
    fee = sum(
        (D(".07") * multiplier * qty * price * (1 - price)).quantize(
            D(".000001"), rounding=ROUND_CEILING
        )
        for price, qty in fills
    )
    debit = (gross + fee).quantize(D(".01"), rounding=ROUND_CEILING)
    return gross, debit


def ceiling(prob, multiplier):
    # Whole-cent watch level; actual displayed subcent orders are evaluated at full precision.
    for cents in range(99, 0, -1):
        _, debit = order_cost([(D(cents) / 100, D(SIZE))], multiplier)
        if D(str(prob)) * SIZE > debit:
            return cents
    return 0


def walk(levels, multiplier):
    """Buy YES against NO bids or buy NO against YES bids; never combine separate contracts."""
    remaining = D(SIZE)
    fills = []
    for bid, qty in sorted(((D(str(p)), D(str(q))) for p, q in levels), reverse=True):
        if not 0 < bid < 1 or qty <= 0:
            raise ValueError("Invalid book level")
        take = min(qty, remaining)
        fills.append((1 - bid, take))
        remaining -= take
        if not remaining:
            break
    if remaining:
        return None
    gross, debit = order_cost(fills, multiplier)
    return {
        "qty": SIZE,
        "ask_c": float(gross * 100 / SIZE),
        "fee_usd": float(debit - gross),
        "debit_usd": float(debit),
        "fills": [[str(p), str(q)] for p, q in fills],
    }
