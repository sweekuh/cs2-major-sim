"""Inter-stage seed-derivation gate — engine/seeding.py (SEED-01 / SEED-02).

THE correctness gate for Phase 7 Slice 2a: ``test_seed_derivation_is_deterministic``
asserts identical prior-stage finals + invited list -> BYTE-IDENTICAL Stage-2 seeds
across two independent ``seed_next_stage`` calls (no RNG, no file I/O, no dict/set
iteration-order dependence). The merge test proves the VERIFIED Valve rule (invited take
seeds 1-8 by VRS rank; the 8 qualifiers take 9-16 by the literal final-standings chain —
NOT interleaved); the tie + loss-bucket tests pin the literal ``(losses, -difficulty,
prior_seed)`` chain (Open Question 1 resolution); two source guards enforce the canonical
``engine.probs.difficulty`` import (no second Buchholz copy, ENG-03) and module purity.

The deterministic full-lock replay idiom (``simulate_stage(..., locked, pairings_out=[])``
returns ``{id: Team}`` with ``.opps`` populated) mirrors tests/test_backtest_budapest_2025.py
and engine/live.py::derive_bracket.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from engine.probs import difficulty
from engine.seeding import InvitedTeam, seed_next_stage
from engine.swiss import simulate_stage
from engine.teams import ADVANCE_AT_WINS, Team

FIXTURE = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "budapest_2025_stage1.json"
)


# ---------------------------------------------------------------------------
# Deterministic prior-stage replay helper (the {id: Team} seeding consumes).
# ---------------------------------------------------------------------------
def _build_finished_stage1_replay() -> dict[int, Team]:
    """Replay a fully-locked Budapest 2025 Stage 1 -> {id: Team} with .opps populated.

    Builds the ``locked`` winner dict from the fixture via the same
    ``locked[frozenset((w, ell))] = w`` idiom test_backtest_budapest_2025.py uses, then runs
    the SHIPPED ``simulate_stage`` once with a throwaway rng (a fully-locked stage never
    samples -> deterministic). The returned Teams carry final .wins/.losses AND the opponent
    OBJECT set ``difficulty()`` needs. Exactly 8 finish at 3 wins (the verified advancers).
    """
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    seeding = {int(s): name for s, name in fx["seeding"].items()}
    name_to_seed = {name: s for s, name in seeding.items()}
    teams = [Team(id=s, name=name, seed=s, rating=50.0) for s, name in seeding.items()]

    locked: dict[frozenset, int] = {}
    for rnd in fx["rounds"]:
        for m in rnd["matches"]:
            w, ell = name_to_seed[m["winner"]], name_to_seed[m["loser"]]
            locked[frozenset((w, ell))] = w

    rng = np.random.default_rng(0)  # throwaway: fully-locked stage is deterministic
    return simulate_stage(teams, None, 40.0, rng, locked, pairings_out=[])


def _fixed_invited_8() -> list[InvitedTeam]:
    """8 [INFERRED] Stage-2 invited descriptors (name, vrs_rank, rating).

    Returned out of VRS-rank order on purpose so the merge/determinism tests prove
    seed_next_stage imposes the (vrs_rank, name) order itself rather than echoing input order.
    """
    return [
        InvitedTeam(name="Vitality", vrs_rank=1, rating=95.0),
        InvitedTeam(name="Spirit", vrs_rank=2, rating=90.0),
        InvitedTeam(name="MOUZ", vrs_rank=3, rating=84.0),
        InvitedTeam(name="Aurora", vrs_rank=4, rating=80.0),
        InvitedTeam(name="The MongolZ", vrs_rank=5, rating=82.0),
        InvitedTeam(name="Natus Vincere", vrs_rank=6, rating=79.0),
        InvitedTeam(name="G2", vrs_rank=7, rating=83.0),
        InvitedTeam(name="FURIA", vrs_rank=8, rating=70.0),
    ][::-1]  # reversed -> input order is NOT the seed order


# ---------------------------------------------------------------------------
# Synthetic qualifier sets (hand-worked .opps so difficulty() is exactly known).
# ---------------------------------------------------------------------------
def _qualifier(name: str, seed: int, *, wins: int, losses: int, opp_margin: int) -> Team:
    """A finished qualifier with EXACTLY one synthetic opponent whose (w-l) == opp_margin.

    difficulty(t) == sum(o.wins - o.losses for o in t.opps), so a single opponent at
    (opp_margin, 0) gives difficulty(t) == opp_margin — a hand-computable Buchholz.
    """
    t = Team(id=seed, name=name, seed=seed, rating=60.0, wins=wins, losses=losses)
    t.opps = {Team(id=900 + seed, name=f"opp-{name}", seed=900 + seed, rating=50.0,
                   wins=max(opp_margin, 0), losses=max(-opp_margin, 0))}
    return t


def _eight_qualifiers(specs: list[tuple[str, int, int, int, int]]) -> dict[int, Team]:
    """Build a {id: Team} map of exactly 8 advancers from (name, seed, wins, losses, margin)."""
    assert len(specs) == 8
    return {
        seed: _qualifier(name, seed, wins=w, losses=ell, opp_margin=margin)
        for (name, seed, w, ell, margin) in specs
    }


def _stage2_seed_of(seeds: list[Team], name: str) -> int:
    return next(t.seed for t in seeds if t.name == name)


# ===========================================================================
# SEED-02 — the determinism gate (THE correctness gate; never loosen it).
# ===========================================================================
def test_seed_derivation_is_deterministic():
    """SEED-02 GATE: identical prior-stage finals + invited list -> BYTE-IDENTICAL Stage-2
    seeds across two independent seed_next_stage calls. No RNG, no file I/O, no dict/set
    iteration-order dependence. Also asserts the derived seed sequence is exactly 1..16."""
    prior_finals = _build_finished_stage1_replay()
    invited = _fixed_invited_8()
    a = seed_next_stage(prior_finals, invited)
    b = seed_next_stage(prior_finals, invited)
    assert [(t.seed, t.name, t.rating) for t in a] == [(t.seed, t.name, t.rating) for t in b]
    assert [t.seed for t in a] == list(range(1, 17))  # exactly seeds 1..16


def test_derivation_yields_exactly_16_teams():
    """A complete 16-team finished replay -> exactly 8 qualifiers -> a 16-team derived list
    (8 invited + 8 qualifiers); a non-16 list is impossible (T-07-06)."""
    prior_finals = _build_finished_stage1_replay()
    qualifiers = [t for t in prior_finals.values() if t.wins >= ADVANCE_AT_WINS]
    assert len(qualifiers) == 8
    seeds = seed_next_stage(prior_finals, _fixed_invited_8())
    assert len(seeds) == 16


# ===========================================================================
# SEED-01 — the VERIFIED Valve merge rule (invited 1-8 / qualifiers 9-16).
# ===========================================================================
def test_invited_take_seeds_1_8_qualifiers_9_16():
    """SEED-01 (VERIFIED Valve rule): invited occupy seeds 1-8 (VRS order), the 8 qualifiers
    occupy seeds 9-16 (final prior-stage chain) — NOT interleaved. No invited name appears in
    9-16 and no qualifier in 1-8."""
    prior_finals = _build_finished_stage1_replay()
    invited = _fixed_invited_8()
    seeds = seed_next_stage(prior_finals, invited)
    invited_names = {iv.name for iv in invited}
    qualifier_names = {t.name for t in prior_finals.values() if t.wins >= ADVANCE_AT_WINS}

    assert all(seeds[i].name in invited_names for i in range(8))  # seeds 1-8 invited
    assert all(seeds[i].name in qualifier_names for i in range(8, 16))  # seeds 9-16 qualifiers
    assert all(seeds[i].name not in invited_names for i in range(8, 16))
    assert all(seeds[i].name not in qualifier_names for i in range(8))


def test_invited_seeds_follow_vrs_rank_order():
    """Seeds 1-8 are the invited teams in ASCENDING vrs_rank order (lower rank = better seed),
    regardless of the order they were passed in."""
    prior_finals = _build_finished_stage1_replay()
    invited = _fixed_invited_8()
    seeds = seed_next_stage(prior_finals, invited)
    expected = [iv.name for iv in sorted(invited, key=lambda iv: (iv.vrs_rank, iv.name))]
    assert [seeds[i].name for i in range(8)] == expected


# ===========================================================================
# Literal (losses, -difficulty, prior_seed) chain (Open Question 1 resolution).
# ===========================================================================
def test_qualifier_tie_breaks_on_prior_seed():
    """Two qualifiers with the SAME losses AND equal difficulty() but prior Stage-1 seeds 3 and
    7 -> the prior-seed-3 team gets the earlier (lower) Stage-2 seed. The final discriminator
    (prior_seed ascending) resolves an otherwise-exact tie deterministically."""
    # Two 3-1 advancers with equal Buchholz (margin 2) and prior seeds 3 vs 7; six fillers.
    prior_finals = _eight_qualifiers([
        ("TieSeed3", 3, 3, 1, 2),
        ("TieSeed7", 7, 3, 1, 2),
        ("Fill0", 1, 3, 0, 5),  # 3-0, outranks the 3-1 pair on losses
        ("Fill1", 2, 3, 1, 4),  # 3-1 higher Buchholz -> above the tied pair
        ("Fill2", 4, 3, 1, 1),  # 3-1 lower Buchholz -> below the tied pair
        ("Fill3", 5, 3, 2, 3),  # 3-2 -> below all 3-1
        ("Fill4", 6, 3, 2, 1),
        ("Fill5", 8, 3, 2, 0),
    ])
    # Sanity: the two tied teams really do have equal difficulty.
    assert difficulty(prior_finals[3]) == difficulty(prior_finals[7])
    seeds = seed_next_stage(prior_finals, _fixed_invited_8())
    assert _stage2_seed_of(seeds, "TieSeed3") < _stage2_seed_of(seeds, "TieSeed7")


def test_loss_bucket_outranks_buchholz():
    """A 3-0 advancer with LOWER Buchholz still seeds ABOVE a 3-2 advancer with HIGHER Buchholz:
    losses-ascending dominates difficulty (the literal rulebook chain, Open Question 1)."""
    prior_finals = _eight_qualifiers([
        ("ZeroLossLowBuch", 5, 3, 0, 1),  # 3-0 but Buchholz only 1
        ("TwoLossHighBuch", 1, 3, 2, 9),  # 3-2 but Buchholz 9
        ("A", 2, 3, 1, 5),
        ("B", 3, 3, 1, 4),
        ("C", 4, 3, 1, 3),
        ("D", 6, 3, 2, 6),
        ("E", 7, 3, 2, 2),
        ("F", 8, 3, 1, 0),
    ])
    assert difficulty(prior_finals[5]) < difficulty(prior_finals[1])  # 1 < 9
    seeds = seed_next_stage(prior_finals, _fixed_invited_8())
    assert _stage2_seed_of(seeds, "ZeroLossLowBuch") < _stage2_seed_of(seeds, "TwoLossHighBuch")


def test_higher_buchholz_outranks_within_loss_bucket():
    """Within the same loss bucket (both 3-1), the higher Difficulty Score seeds above the
    lower one (difficulty descending is the second key)."""
    prior_finals = _eight_qualifiers([
        ("HighBuch31", 4, 3, 1, 7),
        ("LowBuch31", 2, 3, 1, 1),
        ("Z0", 1, 3, 0, 5),
        ("Z1", 3, 3, 0, 3),
        ("Z2", 5, 3, 2, 4),
        ("Z3", 6, 3, 2, 2),
        ("Z4", 7, 3, 2, 1),
        ("Z5", 8, 3, 2, 0),
    ])
    seeds = seed_next_stage(prior_finals, _fixed_invited_8())
    assert _stage2_seed_of(seeds, "HighBuch31") < _stage2_seed_of(seeds, "LowBuch31")


def test_non_complete_replay_fails_loud():
    """Fewer than 8 advancers (an incomplete / non-terminated stage) -> seed_next_stage raises
    rather than silently emitting a short list (Pitfall 5 / T-07-06)."""
    seven = _eight_qualifiers([
        ("Q1", 1, 3, 0, 5), ("Q2", 2, 3, 1, 4), ("Q3", 3, 3, 1, 3), ("Q4", 4, 3, 1, 2),
        ("Q5", 5, 3, 2, 1), ("Q6", 6, 3, 2, 0), ("Q7", 7, 3, 2, 2), ("Q8", 8, 3, 2, 1),
    ])
    del seven[8]  # drop one advancer -> only 7 qualifiers
    import pytest

    with pytest.raises((AssertionError, ValueError)):
        seed_next_stage(seven, _fixed_invited_8())


# ===========================================================================
# Source guards — canonical Buchholz (ENG-03) + module purity (SEED-02).
# ===========================================================================
def test_buchholz_uses_canonical_difficulty():
    """ENG-03: seeding imports engine.probs.difficulty — NO second copy. The module source
    contains the canonical import and no inline 'o.wins - o.losses' / 'opp.wins - opp.losses'
    Buchholz re-implementation."""
    import engine.seeding as s

    src = open(s.__file__, encoding="utf-8").read()
    assert "from engine.probs import difficulty" in src
    assert "o.wins - o.losses" not in src
    assert "opp.wins - opp.losses" not in src


def test_seeding_is_pure():
    """SEED-02 purity guard (mirrors test_mc.py::test_no_forbidden_imports): seeding.py imports
    no streamlit/httpx/requests and makes no RNG call (no default_rng / np.random) that could
    affect output — referentially transparent so the determinism gate verifies it in isolation."""
    import engine.seeding as s

    src = open(s.__file__, encoding="utf-8").read()
    for forbidden in ("import streamlit", "import httpx", "import requests"):
        assert forbidden not in src
    assert "default_rng" not in src
    assert "np.random" not in src
