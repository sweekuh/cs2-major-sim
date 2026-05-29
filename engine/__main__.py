"""Headless Walking Skeleton smoke run: ``uv run python -m engine [N]``.

The "one real interaction" that proves the full Phase-1 pipeline (fixtures -> swiss ->
MC -> probs) runs locally: load the default [INFERRED] Cologne teams, run N stage sims
through the proven swiss engine via run_mc_progressive, and print a per-team table of
P(3-0)/P(advance)/P(0-3) each with its hand-coded Wilson band, plus the invariant sums
(ΣP(3-0)≈2, ΣP(0-3)≈2, ΣP(advance)≈8).

Dependency-light (no streamlit/httpx) — this is the functional-core CLI. A FIXED seed
makes the run reproducible (ENG-09); N is overridable via argv. argv N is validated as a
positive int and capped (T-03-02: never crash or hang on negative/huge/NaN input).
"""

from __future__ import annotations

import sys

from engine.montecarlo import run_mc_progressive, Result
from engine.teams import load_teams

DEFAULT_SMOKE_N = 50_000  # fast smoke default; large enough for invariants ±0.05
SMOKE_SEED = 20260528  # fixed -> reproducible smoke run
MAX_N = 5_000_000  # cap: reject absurd N rather than hang (T-03-02 DoS mitigation)


def _parse_n(argv: list[str]) -> int:
    """Parse an optional N from argv, validated as a positive int within MAX_N (T-03-02).

    Rejects negatives, zero, non-integers (incl. NaN/float strings), and values above the
    cap — a positive-int statistical sim count only, never used for secrets.
    """
    if len(argv) < 2:
        return DEFAULT_SMOKE_N
    raw = argv[1]
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise SystemExit(f"N must be a positive integer, got {raw!r}")
    if n <= 0:
        raise SystemExit(f"N must be a positive integer, got {n}")
    if n > MAX_N:
        raise SystemExit(f"N too large (max {MAX_N:,}), got {n:,}")
    return n


def _drain(teams, N: int) -> Result:
    """Drain the progress generator (as the Phase-2 cached wrapper will) -> final Result."""
    gen = run_mc_progressive(teams, None, 40.0, N, {}, seed=SMOKE_SEED)
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


def _fmt_band(band: tuple[float, float]) -> str:
    lo, hi = band
    return f"[{lo:6.3f}, {hi:6.3f}]"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    N = _parse_n(argv)
    teams = load_teams()
    name_by_id = {t.id: t.name for t in teams}

    result = _drain(teams, N)
    p_30, p_adv, p_03 = result.p_30(), result.p_advance(), result.p_03()

    print(f"Cologne 2026 Stage 1 - Monte Carlo  (N={N:,}, seed={SMOKE_SEED})\n")
    header = (
        f"{'Team':<20} "
        f"{'P(3-0)':>7} {'Wilson':>16}  "
        f"{'P(adv)':>7} {'Wilson':>16}  "
        f"{'P(0-3)':>7} {'Wilson':>16}"
    )
    print(header)
    print("-" * len(header))
    # Sort by P(advance) desc for an eyeball-sane table (GamerLegion should top it).
    for tid in sorted(p_adv, key=lambda i: p_adv[i], reverse=True):
        print(
            f"{name_by_id[tid]:<20} "
            f"{p_30[tid]:7.3f} {_fmt_band(result.band_30[tid]):>16}  "
            f"{p_adv[tid]:7.3f} {_fmt_band(result.band_advance[tid]):>16}  "
            f"{p_03[tid]:7.3f} {_fmt_band(result.band_03[tid]):>16}"
        )

    sum_30 = sum(p_30.values())
    sum_adv = sum(p_adv.values())
    sum_03 = sum(p_03.values())
    print("-" * len(header))
    print(
        f"Invariants:  sum P(3-0)={sum_30:.3f} (~2)   "
        f"sum P(advance)={sum_adv:.3f} (~8)   "
        f"sum P(0-3)={sum_03:.3f} (~2)"
    )
    ok = (
        abs(sum_30 - 2.0) <= 0.05
        and abs(sum_adv - 8.0) <= 0.05
        and abs(sum_03 - 2.0) <= 0.05
    )
    print("Invariants hold within +/-0.05." if ok else "WARNING: invariants out of tolerance!")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
