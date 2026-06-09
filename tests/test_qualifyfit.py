"""Qualify-market calibration guards (QFIT-01/02) — engine.qualifyfit + scripts.fit_qualify.

The revert-proof bar (LESSONS meta-lesson: a regression test must fail when the wrong rule is
applied):

  - synthetic recovery: targets generated from KNOWN ratings are recovered from a FLAT start —
    fails if the logit stepper / gauge / sim plumbing is wrong in any way that moves probs;
  - determinism: identical inputs -> byte-identical fitted dicts (common-random-numbers seed
    discipline) — fails if any iteration draws from an unpinned stream;
  - gauge: the top seed (min id) keeps its base rating — fails if the re-centering is dropped;
  - validation: garbage targets (missing id, p outside (0,1), sum outside [7,9]) raise
    ValueError; a vig-ish sum (8.4) is accepted and renormalized — fails if the fail-loud
    contract silently fits garbage;
  - all_bo3 + market_blend threading: spy on the simulate_stage call — fails if either flag
    stops reaching the engine (the R1-priced-from-market orthogonality fact);
  - the CLI writes fitted_ratings + _meta.qualify_fit ADDITIVELY (version stays 1, every other
    key preserved), errors clean on a missing "qualify" block or a _meta.stage mismatch.

NO test here reads data/odds_cache.json (a gitignored runtime artifact) — caches are tmp_path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.montecarlo import run_mc
from engine.qualifyfit import _simulate_qualify_probs, fit_qualify_ratings
from engine.teams import load_stage, load_teams

REPO = Path(__file__).resolve().parent.parent


def _flat(teams, r=50.0):
    return {t.id: r for t in teams}


def _uniform_targets(teams, p=0.5):
    return {t.id: p for t in teams}


# ---------------------------------------------------------------------------
# (a) synthetic recovery — the end-to-end correctness proof
# ---------------------------------------------------------------------------
def test_synthetic_recovery_from_flat_start():
    """Targets simulated from a KNOWN ratings vector (N=30k) are recovered by fitting from a
    FLAT start: the fitted ratings' independently re-simulated qualify probs match the targets
    within 0.025 and the diagnostics report convergence. This is the whole feature — it fails
    on any wrong step direction, scale, gauge, or sim wiring."""
    teams = load_teams()
    true = {t.id: 50.0 + (8 - t.id) * 2.5 for t in teams}  # known, well-spread truth
    targets = run_mc(teams, true, 40.0, 30_000, locked={}, seed=99).p_advance()

    fitted, diag = fit_qualify_ratings(
        teams, 40.0, {}, targets,
        base_ratings=_flat(teams), n_per_iter=8_000, max_iters=12, tol=0.02,
    )
    assert diag["converged"] is True
    assert diag["max_err"] <= 0.02
    assert diag["iters"] <= 12

    # Independent verification: a FRESH sim (different seed than both the target generation and
    # the fit's common-random-numbers stream) reprices the targets within ~0.025.
    verify = run_mc(teams, fitted, 40.0, 30_000, locked={}, seed=12345).p_advance()
    max_err = max(abs(verify[tid] - targets[tid]) for tid in targets)
    assert max_err <= 0.025, f"fitted ratings reprice qualify targets to {max_err:.4f} > 0.025"


# ---------------------------------------------------------------------------
# (b) determinism — common random numbers, fixed seed per iteration
# ---------------------------------------------------------------------------
def test_fit_is_deterministic():
    """Two identical fit calls return byte-identical fitted dicts AND diagnostics — the fixed
    per-iteration seed (common random numbers) makes the whole fit a pure function of its
    inputs. Fails if any iteration draws from an unpinned RNG stream."""
    teams = load_teams()
    targets = {t.id: (0.75 if t.id <= 8 else 0.25) for t in teams}
    kw = dict(base_ratings=_flat(teams), n_per_iter=2_000, max_iters=3, tol=1e-6)

    f1, d1 = fit_qualify_ratings(teams, 40.0, {"1-9": 0.7}, targets, **kw)
    f2, d2 = fit_qualify_ratings(teams, 40.0, {"1-9": 0.7}, targets, **kw)
    assert f1 == f2  # exact float equality — determinism, not approximation
    assert d1 == d2


# ---------------------------------------------------------------------------
# (c) gauge — the anchor team's rating is pinned to its base value
# ---------------------------------------------------------------------------
def test_gauge_anchor_keeps_base_rating():
    """The top seed (min id) keeps its base rating EXACTLY after the fit — the additive
    null-space pin mirroring fit_ratings' anchor convention. tol is set unreachable so real
    steps happen; fails if the per-step re-centering is dropped."""
    teams = load_teams()
    targets = {t.id: (0.8 if t.id <= 8 else 0.2) for t in teams}
    fitted, _ = fit_qualify_ratings(
        teams, 40.0, {}, targets,
        base_ratings=_flat(teams, 50.0), n_per_iter=1_000, max_iters=3, tol=1e-9,
    )
    assert fitted[min(t.id for t in teams)] == 50.0
    # …and the other ratings actually moved (the pin is not a no-op fit).
    assert any(fitted[t.id] != 50.0 for t in teams)


def test_default_base_is_fixture_rating():
    """With no base_ratings the fit starts from (and anchors to) each team's fixture rating."""
    teams = load_teams()
    targets = {t.id: (0.8 if t.id <= 8 else 0.2) for t in teams}
    fitted, _ = fit_qualify_ratings(
        teams, 40.0, {}, targets, n_per_iter=500, max_iters=2, tol=1e-9
    )
    anchor = min(teams, key=lambda t: t.id)
    assert fitted[anchor.id] == float(anchor.rating)


# ---------------------------------------------------------------------------
# (d) validation — fail LOUD on garbage targets (never silently fit them)
# ---------------------------------------------------------------------------
def test_targets_must_cover_all_team_ids():
    teams = load_teams()
    targets = _uniform_targets(teams)
    targets.pop(7)  # missing one team id
    with pytest.raises(ValueError, match="exactly"):
        fit_qualify_ratings(teams, 40.0, {}, targets, n_per_iter=100, max_iters=1)
    targets[7] = 0.5
    targets[99] = 0.5  # extra unknown id
    with pytest.raises(ValueError, match="exactly"):
        fit_qualify_ratings(teams, 40.0, {}, targets, n_per_iter=100, max_iters=1)


@pytest.mark.parametrize("bad_p", [0.0, 1.0, 1.2, -0.1])
def test_targets_must_be_strictly_inside_unit_interval(bad_p):
    teams = load_teams()
    targets = _uniform_targets(teams)
    targets[3] = bad_p
    with pytest.raises(ValueError, match=r"\(0, 1\)"):
        fit_qualify_ratings(teams, 40.0, {}, targets, n_per_iter=100, max_iters=1)


def test_target_sum_far_from_8_is_rejected():
    """Sum 5.0 is structurally impossible for qualify probs (they sum to 8) beyond any plausible
    vig — refuse to fit garbage, fail loud (never a confidently-wrong calibration)."""
    teams = load_teams()
    targets = _uniform_targets(teams, 5.0 / 16.0)  # sums to exactly 5.0
    with pytest.raises(ValueError, match="sum"):
        fit_qualify_ratings(teams, 40.0, {}, targets, n_per_iter=100, max_iters=1)


def test_target_sum_with_vig_is_renormalized():
    """Sum 8.4 (markets carry vig/noise) is ACCEPTED and renormalized to exactly 8 before
    fitting — diagnostics report the raw sum, and the fit runs without raising."""
    teams = load_teams()
    targets = _uniform_targets(teams, 8.4 / 16.0)  # sums to exactly 8.4
    fitted, diag = fit_qualify_ratings(
        teams, 40.0, {}, targets, base_ratings=_flat(teams), n_per_iter=500, max_iters=1
    )
    assert diag["target_sum"] == pytest.approx(8.4)
    assert set(fitted) == {t.id for t in teams}
    # Renormalized uniform targets are 0.5 each == a FLAT field's qualify prob, so the flat
    # start already sits at the (renormalized) targets up to MC noise — proving the fit ran
    # against 8/sum-scaled targets, not the raw 0.525s (which would sit 0.025 off plus noise).
    assert diag["max_err"] < 0.1


# ---------------------------------------------------------------------------
# (e) engine threading — all_bo3 + the R1 market prices reach simulate_stage
# ---------------------------------------------------------------------------
def _spy_simulate_stage(monkeypatch):
    """Patch the simulate_stage reference qualifyfit bound at import; record kwargs, delegate."""
    import engine.qualifyfit as qf

    calls = {"all_bo3": [], "market_overrides": []}
    real = qf.simulate_stage

    def _rec(*args, **kwargs):
        calls["all_bo3"].append(kwargs.get("all_bo3", "ABSENT"))
        calls["market_overrides"].append(kwargs.get("market_overrides", "ABSENT"))
        return real(*args, **kwargs)

    monkeypatch.setattr(qf, "simulate_stage", _rec)
    return calls


def test_all_bo3_flag_reaches_the_engine(monkeypatch):
    """all_bo3=True is threaded into every simulate_stage call (the Stage-3 mode) — fails if
    the flag is dropped between the fit and the engine."""
    teams, cfg = load_stage("data/stage3.json")
    assert cfg.get("all_bo3") is True  # the fixture fact the CLI derives the flag from
    calls = _spy_simulate_stage(monkeypatch)
    fit_qualify_ratings(
        teams, 40.0, {}, _uniform_targets(teams),
        all_bo3=True, n_per_iter=20, max_iters=1,
    )
    assert calls["all_bo3"] and all(v is True for v in calls["all_bo3"])


def test_market_blend_prices_r1_inside_the_sim(monkeypatch):
    """Every sim receives the R1 market prices as ``market_overrides`` — the orthogonality
    fact (R1 priced from the market, ratings only steer rounds 2-5). Accepts both the CLI's
    p-only shape and the app's (p, var) blend shape. Fails if market_blend stops reaching
    simulate_stage."""
    teams = load_teams()
    for blend in ({"1-9": 0.78, "2-10": 0.43}, {"1-9": (0.78, 0.004), "2-10": (0.43, 0.001)}):
        calls = _spy_simulate_stage(monkeypatch)
        fit_qualify_ratings(
            teams, 40.0, blend, _uniform_targets(teams), n_per_iter=20, max_iters=1
        )
        assert calls["market_overrides"], "the fit must run sims"
        assert all(
            ov == {"1-9": 0.78, "2-10": 0.43} for ov in calls["market_overrides"]
        ), f"R1 market prices must reach simulate_stage as overrides; got {calls['market_overrides'][:1]}"


def test_all_bo3_small_case_converges():
    """Cheap end-to-end all-Bo3 sanity: targets generated under all_bo3=True + an R1 blend are
    re-fit (from the true base, so it converges immediately) — completes and converges."""
    teams, _ = load_stage("data/stage3.json")
    blend = {"1-9": 0.78, "2-10": 0.43}
    true = {t.id: float(t.rating) for t in teams}
    targets = _simulate_qualify_probs(
        teams, true, 40.0, blend, all_bo3=True, n=6_000, seed=7
    )
    fitted, diag = fit_qualify_ratings(
        teams, 40.0, blend, targets, all_bo3=True, n_per_iter=4_000, max_iters=6, tol=0.03
    )
    assert diag["converged"] is True
    assert set(fitted) == {t.id for t in teams}


# ---------------------------------------------------------------------------
# (f) scripts.fit_qualify — the additive cache writer
# ---------------------------------------------------------------------------
def _stage3_cache(tmp_path, *, qualify=True, stage=3):
    """A valid v1 stage-3 odds cache with blended R1 markets, an extra foreign key, and
    (optionally) the operator-authored qualify block."""
    cache = {
        "_meta": {
            "fetched_at": "2026-06-09T12:00:00+00:00",
            "version": 1,
            "providers_present": ["kalshi"],
            "round_hint": 1,
            "stage": stage,
        },
        "blended": {
            "1-9": {"p": 0.78, "var": 0.0046, "n_sources": 2, "bo3": True},
            "2-10": {"p": 0.43, "var": 0.0015, "n_sources": 2, "bo3": True},
        },
        "extra_blob": {"keep": "me"},  # foreign additive key — must survive byte-for-byte
    }
    if qualify:
        cache["qualify"] = {
            str(i): (0.72 if i <= 8 else 0.28) for i in range(1, 17)
        }  # sums to 8.0
    p = tmp_path / "odds_cache.json"
    p.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return p, cache


def test_script_writes_additive_keys_and_preserves_everything_else(tmp_path):
    """main() writes fitted_ratings (engine-id STRING keys, all 16) + _meta.qualify_fit, keeps
    version 1, and preserves every pre-existing key — the additive-within-v1 contract that
    keeps the app's version-locked loader accepting the cache."""
    from scripts.fit_qualify import main

    path, original = _stage3_cache(tmp_path)
    returned = main(path, "stage3", n_per_iter=300, max_iters=2)

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == returned  # the written cache IS the returned one

    fitted = on_disk["fitted_ratings"]
    assert set(fitted) == {str(i) for i in range(1, 17)}, "engine-id STRING keys, all 16 teams"
    assert all(isinstance(v, float) for v in fitted.values())

    fit_meta = on_disk["_meta"]["qualify_fit"]
    assert set(fit_meta) >= {"at", "iters", "max_err", "converged"}
    assert isinstance(fit_meta["converged"], bool)

    # Everything that existed before is preserved; the schema version did NOT bump.
    assert on_disk["_meta"]["version"] == 1
    assert on_disk["blended"] == original["blended"]
    assert on_disk["qualify"] == original["qualify"]
    assert on_disk["extra_blob"] == original["extra_blob"]
    assert on_disk["_meta"]["fetched_at"] == original["_meta"]["fetched_at"]
    assert on_disk["_meta"]["stage"] == 3


def test_script_missing_qualify_block_errors_clean(tmp_path):
    """No 'qualify' block -> a clean ValueError naming the missing key (and the __main__
    wrapper turns it into a nonzero exit) — never a half-written cache."""
    from scripts.fit_qualify import main

    path, original = _stage3_cache(tmp_path, qualify=False)
    with pytest.raises(ValueError, match="qualify"):
        main(path, "stage3", n_per_iter=100, max_iters=1)
    # The cache was not touched by the failed run.
    assert json.loads(path.read_text(encoding="utf-8")) == original


def test_script_stage_mismatch_errors(tmp_path):
    """_meta.stage=1 cache + --stage stage3 -> fail LOUD (the cross-stage mis-join guard:
    engine ids name different teams each stage)."""
    from scripts.fit_qualify import main

    path, _ = _stage3_cache(tmp_path, stage=1)
    with pytest.raises(ValueError, match="stage"):
        main(path, "stage3", n_per_iter=100, max_iters=1)


def test_cli_missing_qualify_exits_nonzero(tmp_path):
    """The argparse __main__ path: missing 'qualify' prints a clear message and exits nonzero
    (the operator-facing contract; python -m scripts.fit_qualify)."""
    path, _ = _stage3_cache(tmp_path, qualify=False)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.fit_qualify", "--stage", "stage3",
         "--cache", str(path), "--n", "100", "--iters", "1"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode != 0
    assert "qualify" in proc.stderr.lower()
