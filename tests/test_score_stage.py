"""Tests for scripts/score_stage.py — the post-stage calibration scorecard.

The GOLDEN regression scores the REAL Cologne 2026 Stage-1 results (the frozen
tests/fixtures/cologne_2026_stage1_results.json) against the shipped data/stage1.json
prior ratings. The expected numbers (n=33, favorite-accuracy 24/33, log-loss 0.5785 at
S=40, argmin S=40 over the sweep) were INDEPENDENTLY computed and verified — if the
scorer's replay or Bo3 inference drifts, these go red. Per the LESSONS meta-lesson, a
failure here means the CODE is wrong: investigate the replay, do not adjust the goldens.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from engine.teams import load_stage
from scripts.score_stage import (
    Match,
    load_results_rows,
    replay_matches,
    score,
    sweep,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cologne_2026_stage1_results.json"

S_SWEEP = [20, 30, 40, 50, 60, 80, 100]


def _stage1_matches_and_ratings():
    """Replay the real Stage-1 results against the shipped stage1 fixture priors."""
    teams, cfg = load_stage(_REPO_ROOT / "data" / "stage1.json")
    assert not cfg.get("all_bo3", False), "stage1 is mixed Bo1/Bo3 — all_bo3 must be off"
    rows = json.loads(_FIXTURE.read_text(encoding="utf-8"))["results"]
    matches = replay_matches(rows, teams)
    ratings = {t.id: t.rating for t in teams}
    return matches, ratings


# ---------------------------------------------------------------------------------------
# GOLDEN regression on real data (independently computed — do NOT adjust to fit the code)
# ---------------------------------------------------------------------------------------


def test_golden_stage1_match_count_and_favorite_accuracy():
    """The real Stage-1 replays to exactly 33 matches with the favorite winning 24 of them."""
    matches, ratings = _stage1_matches_and_ratings()
    assert len(matches) == 33

    out = score(matches, ratings, S=40.0)
    assert out["n"] == 33
    # 24/33 exactly — favorite_accuracy is a ratio of integer outcomes (no p==0.5 ties on
    # the real data: every Stage-1 pairing had distinct prior ratings).
    assert out["favorite_accuracy"] == pytest.approx(24 / 33, abs=1e-9)
    assert abs(out["favorite_accuracy"] - 0.727) < 0.001


def test_golden_stage1_log_loss_at_s40():
    """Log-loss at the shipped S=40 prior is 0.5785 (natural log, mean per match)."""
    matches, ratings = _stage1_matches_and_ratings()
    out = score(matches, ratings, S=40.0)
    assert out["log_loss"] == pytest.approx(0.5785, abs=0.002)
    # Sanity bracket: the priors must beat a coinflip on BOTH metrics on the real stage.
    assert out["log_loss"] < math.log(2.0)
    assert out["brier"] < 0.25


def test_golden_stage1_s40_is_argmin_of_log_loss_sweep():
    """Over the sweep [20,30,40,50,60,80,100] the shipped S=40 minimizes log-loss."""
    matches, ratings = _stage1_matches_and_ratings()
    table = sweep(matches, ratings, S_SWEEP)
    assert [row["S"] for row in table] == [float(s) for s in S_SWEEP]
    best = min(table, key=lambda r: r["log_loss"])
    assert best["S"] == 40.0


# ---------------------------------------------------------------------------------------
# Bo3 inference (the replay invariant)
# ---------------------------------------------------------------------------------------


def _synthetic_rows():
    """A 4-team round sequence driving team 1 to 2 wins and team 2 to 2 losses.

    Round 2 then pits 1 (2-0) vs 4 and 2 (0-2) vs 3 — BOTH must infer Bo3 (one step from
    advance / elimination respectively), while every earlier match stays Bo1.
    """
    return [
        {"round_idx": 0, "match": [1, 2], "winner": 1},
        {"round_idx": 1, "match": [1, 3], "winner": 1},  # team 1 reaches 2 wins
        {"round_idx": 1, "match": [2, 4], "winner": 4},  # team 2 reaches 2 losses
        {"round_idx": 2, "match": [1, 4], "winner": 1},  # 2-win side -> Bo3
        {"round_idx": 2, "match": [2, 3], "winner": 3},  # 2-loss side -> Bo3
    ]


def test_bo3_inferred_when_a_side_is_one_step_from_termination(make_team):
    teams = [make_team(i) for i in (1, 2, 3, 4)]
    matches = replay_matches(_synthetic_rows(), teams)
    assert [m.bo3 for m in matches] == [False, False, False, True, True]
    # The replay also preserved lo/hi orientation and winners.
    assert matches[3] == Match(lo=1, hi=4, winner=1, bo3=True)
    assert matches[4] == Match(lo=2, hi=3, winner=3, bo3=True)


def test_all_bo3_forces_bo3_from_round_zero(make_team):
    """With all_bo3=True (the Stage-3 flag) EVERY match is Bo3 — including round 0."""
    teams = [make_team(i) for i in (1, 2, 3, 4)]
    matches = replay_matches(_synthetic_rows(), teams, all_bo3=True)
    assert len(matches) == 5
    assert all(m.bo3 for m in matches)


# ---------------------------------------------------------------------------------------
# Fail-soft row handling (the fetch_results discipline)
# ---------------------------------------------------------------------------------------


def test_garbled_rows_are_dropped_and_the_rest_score(make_team, caplog):
    teams = [make_team(i) for i in (1, 2, 3, 4)]
    rows = [
        {"round_idx": 0, "match": [1, 2], "winner": 1},
        {"round_idx": 0, "match": [3, 4], "winner": 99},  # winner not in match — drop
        {"round_idx": 1, "winner": 3},  # missing match key — drop
        {"round_idx": 1, "match": [1, 99], "winner": 1},  # unknown engine id — drop
        {"match": [2, 3], "winner": 2},  # missing round_idx — drop
        {"round_idx": 1, "match": [3, 4], "winner": 3},  # fine
    ]
    with caplog.at_level("WARNING", logger="scripts.score_stage"):
        matches = replay_matches(rows, teams)
    assert len(matches) == 2, "the two well-formed rows survive; the four garbled ones drop"
    assert [(m.lo, m.hi, m.winner) for m in matches] == [(1, 2, 1), (3, 4, 3)]
    assert sum("dropping garbled result row" in r.message for r in caplog.records) == 4

    # The survivors still score — no raise, finite metrics.
    out = score(matches, {1: 60.0, 2: 50.0, 3: 55.0, 4: 45.0}, S=40.0)
    assert out["n"] == 2
    assert math.isfinite(out["log_loss"]) and math.isfinite(out["brier"])


# ---------------------------------------------------------------------------------------
# Cross-stage guard (importable path)
# ---------------------------------------------------------------------------------------


def test_cross_stage_meta_fails_loud(tmp_path):
    """A results JSON stamped _meta.stage=2 scored as --stage stage1 raises ValueError."""
    p = tmp_path / "results_cache.json"
    p.write_text(json.dumps({
        "_meta": {"fetched_at": "2026-06-09T00:00:00+00:00", "version": 1, "stage": 2},
        "results": [{"round_idx": 0, "match": [1, 9], "winner": 1}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="cross-stage"):
        load_results_rows(p, stage_id="stage1")


def test_matching_meta_stage_and_bare_fixture_shape_both_load(tmp_path):
    """_meta.stage == --stage passes; the bare {"results": [...]} fixture shape passes too."""
    rows = [{"round_idx": 0, "match": [1, 9], "winner": 1}]
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"_meta": {"version": 1, "stage": 1}, "results": rows}))
    assert load_results_rows(cache, stage_id="stage1") == rows

    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"results": rows}))
    assert load_results_rows(bare, stage_id="stage1") == rows


# ---------------------------------------------------------------------------------------
# Determinism (score is pure — no RNG anywhere in the scorer)
# ---------------------------------------------------------------------------------------


def test_score_is_deterministic():
    matches, ratings = _stage1_matches_and_ratings()
    a = score(matches, ratings, S=40.0)
    b = score(matches, ratings, S=40.0)
    assert a == b
    # And via the sweep wrapper too — identical inputs, identical outputs, bit for bit.
    assert sweep(matches, ratings, S_SWEEP) == sweep(matches, ratings, S_SWEEP)
