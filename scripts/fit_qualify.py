"""scripts/fit_qualify.py — offline qualify-market calibration writer (QFIT-02).

Structural twin of ``scripts/fetch_odds.py``: argparse ``__main__``, NO streamlit, fail-LOUD on
structurally-wrong inputs (this is an explicit operator action, not a render path). It reads
``data/odds_cache.json``, fits per-team ratings so the simulated P(qualify) matches the cache's
``"qualify"`` targets (``engine.qualifyfit.fit_qualify_ratings`` — R1 priced from ``"blended"``,
rounds 2-5 rating-driven), and writes TWO ADDITIVE keys back into the SAME cache file:

    "fitted_ratings": {"<team_id>": rating}          (engine-id string keys, mirroring blended)
    "_meta"."qualify_fit": {"at", "iters", "max_err", "converged"}

Both are ADDITIVE within schema v1 (NOT a version bump — a bump would make the app's
version-locked loader reject the cache; the precedent is ``sources``/``stage``). Every other key
is preserved byte-for-byte at the JSON level (load -> mutate -> dump). The fit runs OFFLINE here
— not in the app — because each fit is ``max_iters`` Monte-Carlo passes of ``n_per_iter`` sims,
which has no business inside a Streamlit rerun; the app only READS ``fitted_ratings``
(app._odds_from_cache), fail-soft.

The ``"qualify"`` block (``{"<team_id>": p}``, engine-id string keys like ``blended``'s) is the
operator-supplied qualify-market input; it is itself ADDITIVE within v1. Missing block -> clean
error, nonzero exit. ``_meta.stage`` must match ``--stage`` (the cross-stage guard: engine ids
name DIFFERENT teams each stage, so a cross-stage fit would calibrate the wrong teams).

Usage:
    python -m scripts.fit_qualify --stage stage3 [--cache data/odds_cache.json]
                                  [--n 20000] [--iters 15]
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from engine.qualifyfit import fit_qualify_ratings
from engine.teams import load_stage

# Stage-id helpers shared with the odds fetcher (script -> script import: no ui/streamlit dep,
# and reusing them keeps the writer and this calibrator agreeing on what _meta.stage means).
from scripts.fetch_odds import _STAGE_FIXTURES, _path_for_stage, _stage_number

log = logging.getLogger("scripts.fit_qualify")

DEFAULT_CACHE = "data/odds_cache.json"
DEFAULT_SPREAD = 40.0  # the engine's logistic spread default (PROB-01; app slider default)


def _read_cache(cache_path: Path) -> dict:
    """Load the odds cache fail-LOUD: a missing/garbled/foreign-version cache is an operator
    error here (unlike the app's fail-soft loader — there is nothing to degrade to)."""
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read odds cache {cache_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"odds cache {cache_path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("_meta"), dict):
        raise ValueError(f"odds cache {cache_path} is not a dict with a '_meta' block")
    if raw["_meta"].get("version") != 1:
        raise ValueError(
            f"odds cache {cache_path} has _meta.version {raw['_meta'].get('version')!r}; "
            "this calibrator only writes additive keys into schema version 1"
        )
    return raw


def _qualify_targets(cache: dict, cache_path: Path) -> dict[int, float]:
    """Parse the top-level ``"qualify"`` block into {engine_id: p} — fail-LOUD on absence or a
    malformed entry (a half-parsed target set would silently fit the wrong teams)."""
    qualify = cache.get("qualify")
    if not isinstance(qualify, dict) or not qualify:
        raise ValueError(
            f"odds cache {cache_path} carries no 'qualify' block — add "
            '{"qualify": {"<team_id>": p, ...}} (engine-id string keys, one entry per team) '
            "from the market's qualify markets, then re-run"
        )
    targets: dict[int, float] = {}
    for key, val in qualify.items():
        try:
            targets[int(key)] = float(val)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"malformed 'qualify' entry {key!r}: {val!r} (want engine-id string -> prob)"
            ) from exc
    return targets


def main(
    cache_path: str | Path = DEFAULT_CACHE,
    stage_id: str = "stage3",
    *,
    n_per_iter: int = 20_000,
    max_iters: int = 15,
    spread: float = DEFAULT_SPREAD,
) -> dict:
    """Fit qualify-calibrated ratings and write them back into the cache; returns the cache dict.

    Fail-LOUD (ValueError) on: unreadable/non-v1 cache, a ``_meta.stage`` that does not match
    ``stage_id`` (the cross-stage mis-join guard — engine ids name different teams each stage),
    a missing/malformed ``"qualify"`` block, or garbage targets (delegated to
    ``fit_qualify_ratings``'s validation). The ``__main__`` wrapper turns that into a clear
    message + nonzero exit.
    """
    cache_path = Path(cache_path)
    cache = _read_cache(cache_path)

    # Cross-stage guard (mirrors app._odds_cache_for_active_stage, but LOUD: refusing silently
    # would leave a stale fitted_ratings block in place). Legacy no-stage cache reads as stage 1.
    cache_stage = int(cache["_meta"].get("stage", 1))
    want_stage = _stage_number(stage_id)
    if cache_stage != want_stage:
        raise ValueError(
            f"odds cache {cache_path} is stamped _meta.stage={cache_stage} but --stage "
            f"{stage_id} is stage {want_stage} — engine ids name DIFFERENT teams each stage; "
            "re-fetch odds for this stage (or pass the matching --stage)"
        )

    teams, stage_cfg = load_stage(_path_for_stage(stage_id))
    all_bo3 = bool(stage_cfg.get("all_bo3", False))
    targets = _qualify_targets(cache, cache_path)

    # R1 market prices: p only — var drives the app's epistemic band, not a point fit (K=1).
    # Malformed blended entries are skipped (same fail-soft as the app's read path: the blend is
    # a FETCHED artifact, unlike the operator-authored qualify block).
    market_blend: dict[str, float] = {}
    for key, b in (cache.get("blended") or {}).items():
        try:
            market_blend[str(key)] = float(b["p"])
        except (TypeError, KeyError, ValueError):
            log.warning("skipping malformed blended entry %r", key)

    fitted, diag = fit_qualify_ratings(
        teams, spread, market_blend, targets,
        all_bo3=all_bo3, n_per_iter=n_per_iter, max_iters=max_iters,
    )

    # ADDITIVE write-back (schema stays v1): load -> mutate these two keys -> dump. Every other
    # key rides through the same parsed dict untouched.
    cache["fitted_ratings"] = {str(tid): float(r) for tid, r in fitted.items()}
    cache["_meta"]["qualify_fit"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "iters": diag["iters"],
        "max_err": diag["max_err"],
        "converged": diag["converged"],
    }
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    log.info(
        "fit %d team ratings for %s: iters=%d max_err=%.4f converged=%s -> %s",
        len(fitted), stage_id, diag["iters"], diag["max_err"], diag["converged"], cache_path,
    )
    return cache


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO)
    _ap = argparse.ArgumentParser(
        description="Fit qualify-market-calibrated ratings into data/odds_cache.json"
    )
    _ap.add_argument(
        "--stage", default="stage3", choices=sorted(_STAGE_FIXTURES),
        help="stage the cache's engine-id keys belong to (must match _meta.stage)",
    )
    _ap.add_argument("--cache", default=DEFAULT_CACHE, help="odds cache path to read AND write")
    _ap.add_argument("--n", type=int, default=20_000, help="sims per fit iteration")
    _ap.add_argument("--iters", type=int, default=15, help="max fit iterations")
    _ns = _ap.parse_args()
    try:
        _cache = main(_ns.cache, _ns.stage, n_per_iter=_ns.n, max_iters=_ns.iters)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    _fit = _cache["_meta"]["qualify_fit"]
    print(
        f"fitted_ratings written to {_ns.cache} "
        f"(iters={_fit['iters']}, max_err={_fit['max_err']:.4f}, converged={_fit['converged']})"
    )
    for _tid, _r in sorted(_cache["fitted_ratings"].items(), key=lambda kv: int(kv[0])):
        print(f"  {_tid:>3}: {_r:7.2f}")
