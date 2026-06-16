"""scripts/fit_champion.py — calibrate the playoff ratings to the LIVE champion market (PLAY-04).

Anchors the champion-probability TARGET to the live tournament-winner market, fits the 8 playoff
ratings so the bracket sim reproduces it (``engine.playoff_fit.fit_champion_ratings``), prints the
before/after, and — with ``--write`` — rewrites ``data/playoffs.json``'s ratings in place (seeds
untouched).

WHY (the accuracy rationale): the original playoff ratings were the Stage-3 map priors carried
forward, which ignore the title race the market prices and the bracket draw. Winner futures are the
sharpest crowd-sourced read of the champion outcome; anchoring P(champion) to them THROUGH the real
bracket structure is a strictly better champion estimate (the playoffs' QFIT analog).

TARGET PROVENANCE — LIVE MARKET (post-Stage-3, read 2026-06-16 via WebSearch):
  The live IEM Cologne 2026 winner book over the 8 playoff qualifiers (Polymarket, ~$21M traded;
  Kalshi's KXCS2-IEMCOL26 tracks it but its per-team ladder is bot-blocked from precise extraction,
  so the granular Polymarket reads are used — the two track within a couple points on liquid books).
  These are post-Stage-3 prices: NaVi/MongolZ are eliminated and gone from the book, FURIA repriced
  UP off its 3-0, Vitality cooled from its ~50% pre-event line to the low-40s off its 3-1. Numbers
  are point-in-time reads (+/- ~1-2pp) and renormalized to 1.0 (the raw book sums ~0.92, sub-vig
  rounding). Re-run this script whenever the market moves to re-anchor.
    Vitality 41 · Spirit 27 · FURIA 8.8 · Falcons 6.5 · Aurora 3.8 · G2 2.0 · BetBoom 2.0 · 9z 1.0

Pure numpy + the bracket engine (no streamlit/httpx). Run:
    python -m scripts.fit_champion            # print the fit
    python -m scripts.fit_champion --write    # also rewrite data/playoffs.json ratings
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from engine.bracket import bo_from_stage_cfg, run_playoff_mc
from engine.playoff_fit import fit_champion_ratings
from engine.teams import load_stage

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PLAYOFFS_PATH = _REPO_ROOT / "data" / "playoffs.json"

# Live winner-market prices over the 8 qualifiers, by TEAM NAME (post-Stage-3, 2026-06-16; see the
# module docstring for source + caveats). Renormalized to 1.0 in build_champion_target.
_LIVE_FUTURES: dict[str, float] = {
    "Vitality": 0.410,
    "Spirit": 0.270,
    "FURIA": 0.088,
    "Falcons": 0.065,
    "Aurora": 0.038,
    "G2": 0.020,
    "BetBoom": 0.020,
    "9z": 0.010,
}


def build_champion_target(teams) -> dict[int, float]:
    """The champion target by ENGINE ID: the live winner-market ladder, renormalized to sum 1.0."""
    id_of = {t.name: t.id for t in teams}
    total = sum(_LIVE_FUTURES.values())
    return {id_of[name]: v / total for name, v in _LIVE_FUTURES.items()}


def main(argv: Sequence[str] | None = None) -> dict[int, float]:
    import argparse

    ap = argparse.ArgumentParser(description="Calibrate playoff ratings to the champion futures")
    ap.add_argument("--S", type=float, default=40.0, help="logistic spread (default 40)")
    ap.add_argument("--n", type=int, default=40_000, help="sims per fit iteration (default 40000)")
    ap.add_argument("--write", action="store_true", help="rewrite data/playoffs.json ratings in place")
    ns = ap.parse_args(argv)

    teams, cfg = load_stage(str(_PLAYOFFS_PATH))
    bo = bo_from_stage_cfg(cfg)
    name_of = {t.id: t.name for t in teams}
    target = build_champion_target(teams)

    fitted, diag = fit_champion_ratings(teams, ns.S, target, bo=bo, n_per_iter=ns.n)
    # Verify the fitted ratings reproduce the target in a fresh, larger MC (different seed).
    repro = run_playoff_mc(teams, fitted, ns.S, 80_000, seed=20260616, bo=bo).p_champ()

    print(f"[fit_champion] converged={diag['converged']} iters={diag['iters']} "
          f"max_err={diag['max_err']:.4f}  (S={ns.S}, n_per_iter={ns.n})")
    print(f"  {'team':<10}{'was':>6}{'fitted':>8}{'target':>9}{'sim':>8}")
    for t in sorted(teams, key=lambda t: -target[t.id]):
        print(f"  {name_of[t.id]:<10}{t.rating:>6.0f}{fitted[t.id]:>8.1f}"
              f"{target[t.id]:>9.3f}{repro[t.id]:>8.3f}")

    if ns.write:
        raw = json.loads(_PLAYOFFS_PATH.read_text(encoding="utf-8"))
        for row in raw["teams"]:
            row["rating"] = round(float(fitted[row["seed"]]), 1)
        _PLAYOFFS_PATH.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        print(f"[fit_champion] wrote champion-calibrated ratings to {_PLAYOFFS_PATH}")
    return fitted


if __name__ == "__main__":
    main()
