"""scripts/score_stage.py — the post-stage calibration scorecard (rating-prior audit).

Scores a stage fixture's PRIOR ratings against the stage's REAL match results: for every
finished match it computes the model's pre-match P(lower-id side wins) via the SHIPPED
probability core (``engine.probs.p_map`` -> ``series``, never a re-derivation) and reports
log-loss / Brier / favorite-accuracy, plus a spread (``S``) sweep so a drifting logistic
scale is visible after every stage.

PARTIAL STAGES ARE A USE CASE: the scorer consumes whatever FINISHED matches the results
JSON carries and says how many it scored — a mid-stage audit (e.g. after round 3) is
exactly as valid as a post-stage one, just over fewer matches.

Bo1/Bo3 inference (the replay invariant): the results row schema carries no reliable
``bo`` on the frozen fixtures, so the format is REPLAYED from the Swiss rules — rows are
sorted by ``round_idx`` and win/loss counters replayed; a match is Bo3 iff EITHER side
already has 2 wins or 2 losses (one step from advance/elimination — the Valve rule) OR the
stage fixture declares ``all_bo3: true`` (Stage 3). Getting this wrong silently mis-scores
every elimination match, which is why tests/test_score_stage.py pins the inference on a
synthetic sequence AND on the real Stage-1 goldens.

Fail-soft row handling mirrors scripts/fetch_results.py's discipline: a garbled row
(missing keys, unknown engine id, winner not in the match) is DROPPED + ``log.warning``,
never raised — the rest of the stage still scores.

Cross-stage guard (the LESSONS-Bug-1 class): engine id 5 names a DIFFERENT TEAM each
stage, so scoring a stage-2 results cache against stage-1 ratings would be silently
meaningless. If the results JSON carries ``_meta.stage`` and it mismatches ``--stage``,
this FAILS LOUD (ValueError), mirroring the app's read-side refusal. The bare frozen-
fixture shape (``{"results": [...]}`` with no ``_meta``) is accepted as-is.

Pure stdlib + math + the functional core (engine.probs / engine.teams). NO streamlit,
NO httpx, NO numpy (scripts/ never imports streamlit — repo invariant).

Run:  python -m scripts.score_stage --stage stage1 \
          --results tests/fixtures/cologne_2026_stage1_results.json \
          [--sweep 20,30,40,50,60,80]
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from engine.probs import p_map, series
from engine.teams import load_stage

# Reuse the fetcher's stage-id contracts (ONE fail-loud mapping, never a second copy):
# _path_for_stage resolves the fixture path repo-root-relative; _stage_number is the SAME
# 1-based stamp the fetcher writes into _meta.stage, so the guard below compares like with
# like. scripts.fetch_results' module top imports no httpx/streamlit (lazy-import seam).
from scripts.fetch_results import _path_for_stage, _stage_number

log = logging.getLogger("scripts.score_stage")

# Default results source: the pipeline artifact the fetcher writes (gitignored). The frozen
# test fixture (tests/fixtures/cologne_2026_stage1_results.json) is the hermetic alternative.
DEFAULT_RESULTS = "data/results_cache.json"

# Default spread sweep (centered on the shipped S=40 prior, PROB-01).
DEFAULT_SWEEP = (20.0, 30.0, 40.0, 50.0, 60.0, 80.0)

# Reference lines for the printed scorecard: a coinflip forecaster scores ln 2 log-loss and
# 0.25 Brier on every match — any S beating these means the priors carry real signal.
COINFLIP_LOG_LOSS = math.log(2.0)
COINFLIP_BRIER = 0.25

# Clamp for the log-loss (a p of exactly 0/1 on a wrong call would be -inf; the priors
# never produce one, but score() must stay total on any input).
_EPS = 1e-15

# The "one step from termination" threshold: at 2 wins the next win advances (Bo3); at
# 2 losses the next loss eliminates (Bo3). Matches the Valve Swiss advance-at-3/out-at-3
# format on every shipped stage fixture.
_BO3_THRESHOLD = 2


@dataclass(frozen=True)
class Match:
    """One replayed, scoreable match: the sorted engine-id pair, the winner, the format.

    ``lo < hi`` always (the [lo, hi] row orientation from the frozen cache schema);
    ``winner`` is one of the two; ``bo3`` is the REPLAY-inferred (or all_bo3-forced) format.
    Frozen so a Match can never be mutated between replay and scoring.
    """

    lo: int
    hi: int
    winner: int
    bo3: bool


def replay_matches(rows: Sequence[dict], teams, *, all_bo3: bool = False) -> list[Match]:
    """Replay result rows in round order, inferring each match's Bo1/Bo3 format.

    Sorts by ``round_idx`` (stable — within-round order preserved), then walks the rows
    replaying per-team win/loss counters: a match is Bo3 iff either side already has
    ``_BO3_THRESHOLD`` (2) wins or losses — one step from advance/elimination — OR
    ``all_bo3`` is True (the Stage-3 ``stage.all_bo3`` flag, BO-01).

    Fail-soft (the fetch_results discipline): a garbled row — missing ``round_idx``/
    ``match``/``winner``, a non-pair ``match``, an id not in ``teams``, or a winner that
    is not one of the matched pair — is DROPPED with a ``log.warning``, never raised. A
    dropped row also skips the counter update (we cannot know who won a garbled match),
    so the replayed counters stay consistent with the matches actually scored.
    """
    valid_ids = {t.id for t in teams}

    # Pre-filter rows that can't even be sorted (missing/non-int round_idx) — same drop +
    # warn treatment as any other garbled row, just before the sort instead of inside it.
    sortable: list[dict] = []
    for row in rows:
        try:
            int(row["round_idx"])
        except (KeyError, TypeError, ValueError):
            log.warning("dropping garbled result row (bad/missing round_idx): %r", row)
            continue
        sortable.append(row)
    sortable.sort(key=lambda r: int(r["round_idx"]))  # stable: within-round order kept

    wins = {tid: 0 for tid in valid_ids}
    losses = {tid: 0 for tid in valid_ids}
    matches: list[Match] = []
    for row in sortable:
        try:
            pair = row["match"]
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(f"match is not a 2-list: {pair!r}")
            lo, hi = sorted(int(x) for x in pair)
            winner = int(row["winner"])
            if lo == hi or lo not in valid_ids or hi not in valid_ids:
                raise ValueError(f"unknown/duplicate engine id in match {pair!r}")
            if winner not in (lo, hi):
                raise ValueError(f"winner {winner} not in match [{lo}, {hi}]")
        except Exception as exc:  # noqa: BLE001 — a bad row is DROPPED, never raised
            log.warning("dropping garbled result row (%s): %r", exc, row)
            continue
        bo3 = all_bo3 or any(
            wins[tid] == _BO3_THRESHOLD or losses[tid] == _BO3_THRESHOLD
            for tid in (lo, hi)
        )
        matches.append(Match(lo=lo, hi=hi, winner=winner, bo3=bo3))
        loser = lo if winner == hi else hi
        wins[winner] += 1
        losses[loser] += 1
    return matches


def score(matches: Sequence[Match], ratings: dict[int, float], S: float) -> dict:
    """Score the prior ratings against replayed matches at spread ``S``.

    For each match the model's pre-match probability is
    ``p = series(p_map(r_lo, r_hi, S), bo3)`` — P(the LOWER-id side wins), via the shipped
    core (never re-derived). Returns ``{"n", "log_loss", "brier", "favorite_accuracy"}``:

      - ``log_loss``: mean per-match negative log-likelihood, NATURAL log (coinflip
        reference ln 2 ~= 0.6931); p clamped to (eps, 1-eps) so the metric stays total.
      - ``brier``: mean squared error of p vs the 0/1 outcome (coinflip reference 0.25).
      - ``favorite_accuracy``: fraction of matches where the p>0.5 side won; an exact
        p == 0.5 tie counts as HALF-correct (no side is the favorite, so neither a free
        hit nor a free miss).

    Pure and deterministic — no RNG, no I/O. An empty match list returns n=0 with NaN
    metrics (nothing to average) rather than raising, so a pre-stage call degrades sanely.
    """
    n = len(matches)
    if n == 0:
        nan = float("nan")
        return {"n": 0, "log_loss": nan, "brier": nan, "favorite_accuracy": nan}
    ll = 0.0
    brier = 0.0
    fav = 0.0
    for m in matches:
        p = series(p_map(ratings[m.lo], ratings[m.hi], S), m.bo3)  # P(lo wins)
        y = 1.0 if m.winner == m.lo else 0.0
        pc = min(1.0 - _EPS, max(_EPS, p))
        ll += -(y * math.log(pc) + (1.0 - y) * math.log(1.0 - pc))
        brier += (p - y) ** 2
        if p > 0.5:
            fav += y
        elif p < 0.5:
            fav += 1.0 - y
        else:  # exact coinflip: no favorite — half credit either way
            fav += 0.5
    return {
        "n": n,
        "log_loss": ll / n,
        "brier": brier / n,
        "favorite_accuracy": fav / n,
    }


def sweep(
    matches: Sequence[Match], ratings: dict[int, float], S_values: Sequence[float]
) -> list[dict]:
    """score() across a spread sweep; each row is ``{"S": s, **score(matches, ratings, s)}``."""
    return [{"S": float(s), **score(matches, ratings, s)} for s in S_values]


def load_results_rows(path: str | Path, *, stage_id: str) -> list[dict]:
    """Load result rows from EITHER accepted shape, enforcing the cross-stage guard.

    Accepts both the bare frozen-fixture shape (``{"results": [...]}`` — no ``_meta``) and
    the results-cache shape (``{"_meta": {...}, "results": [...]}``). If ``_meta.stage`` is
    present and differs from ``--stage``'s number, raise ``ValueError`` LOUD — engine ids
    name different teams per stage, so a cross-stage score would be silently meaningless
    (mirrors the app's read-side refusal and the odds seam's stage stamp).

    A results file that is not a dict or has no ``results`` list is also a loud
    ``ValueError`` (an unusable INPUT FILE is an operator error, not a garbled row — the
    fail-soft drop discipline applies per-row, never to the whole artifact).
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"results file {path} must be a JSON object")
    meta = raw.get("_meta")
    if isinstance(meta, dict) and meta.get("stage") is not None:
        cache_stage = int(meta["stage"])
        want = _stage_number(stage_id)
        if cache_stage != want:
            raise ValueError(
                f"cross-stage refusal: results file {path} carries _meta.stage="
                f"{cache_stage} but --stage {stage_id} is stage {want}; engine ids name "
                "different teams per stage, so scoring this would be meaningless"
            )
    rows = raw.get("results")
    if not isinstance(rows, list):
        raise ValueError(f"results file {path} must contain a 'results' list")
    return rows


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry: load fixture + results, replay, sweep, print the scorecard."""
    import argparse

    ap = argparse.ArgumentParser(
        description="Score a stage fixture's PRIOR ratings against the stage's real results"
    )
    ap.add_argument(
        "--stage",
        default="stage1",
        choices=("stage1", "stage2", "stage3", "playoffs"),
        help="stage whose fixture ratings are audited (cross-checked vs _meta.stage)",
    )
    ap.add_argument(
        "--results",
        default=DEFAULT_RESULTS,
        help="results JSON: the fetcher cache (default) or a frozen fixture",
    )
    ap.add_argument(
        "--sweep",
        default=",".join(str(int(s)) for s in DEFAULT_SWEEP),
        help="comma-separated S values to sweep (default: 20,30,40,50,60,80)",
    )
    ns = ap.parse_args(argv)

    teams, stage_cfg = load_stage(_path_for_stage(ns.stage))
    all_bo3 = bool(stage_cfg.get("all_bo3", False))
    ratings = {t.id: t.rating for t in teams}

    try:
        rows = load_results_rows(ns.results, stage_id=ns.stage)
    except FileNotFoundError:
        # Still fail-LOUD (non-zero exit), just with an actionable message instead of a
        # traceback: the default cache is a fetched, gitignored artifact, so its absence
        # is the normal pre-fetch state — point at the fetcher (or the frozen fixture).
        raise SystemExit(
            f"[score_stage] results file not found: {ns.results}\n"
            "  run `python -m scripts.fetch_results` first, or pass --results "
            "tests/fixtures/cologne_2026_stage1_results.json"
        )
    matches = replay_matches(rows, teams, all_bo3=all_bo3)
    dropped = len(rows) - len(matches)

    s_values = [float(s) for s in str(ns.sweep).split(",") if s.strip()]
    table = sweep(matches, ratings, s_values)

    print(
        f"[score_stage] {ns.stage}: scored {len(matches)} match(es) "
        f"({dropped} dropped) from {ns.results}"
        + ("  [all_bo3]" if all_bo3 else "")
    )
    if not matches:
        print("  no finished matches to score yet — nothing to audit")
        return
    print(f"  {'S':>6}  {'log-loss':>9}  {'Brier':>8}  {'fav-acc':>8}")
    for row in table:
        print(
            f"  {row['S']:>6.1f}  {row['log_loss']:>9.4f}  {row['brier']:>8.4f}"
            f"  {row['favorite_accuracy']:>8.4f}"
        )
    best = min(table, key=lambda r: r["log_loss"])
    print(f"  best S by log-loss: {best['S']:.1f} (log-loss {best['log_loss']:.4f})")
    print(
        f"  reference: coinflip log-loss ln2 = {COINFLIP_LOG_LOSS:.4f}, "
        f"Brier = {COINFLIP_BRIER:.4f}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
