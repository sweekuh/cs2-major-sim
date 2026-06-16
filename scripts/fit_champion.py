"""scripts/fit_champion.py — calibrate the playoff ratings to the market's champion futures (PLAY-04).

Constructs a champion-probability TARGET from the best external signal available offline (the
pre-event tournament-winner futures, updated for the Stage-3 finish), fits the 8 playoff ratings so
the bracket sim reproduces it (``engine.playoff_fit.fit_champion_ratings``), prints the before/after,
and — with ``--write`` — rewrites ``data/playoffs.json``'s ratings in place (seeds untouched).

WHY (the accuracy rationale): the shipped playoff ratings were the Stage-3 map priors carried
forward, which ignore the title race the market prices and the bracket draw. Winner futures are the
sharpest crowd-sourced read of the champion outcome; anchoring P(champion) to them THROUGH the real
bracket structure is a strictly better champion estimate (the playoffs' QFIT analog).

TARGET PROVENANCE (documented, not fetched — the build host has no reachable futures provider):
  - Pre-event winner futures (Polymarket, per data/stage3.json's committed comment, 2026-06-09):
    Vitality ~50%, Spirit ~20%, Falcons ~9%, NaVi ~8.4%. NaVi/MongolZ etc. did not make playoffs,
    so the field is renormalized over the 8 qualifiers; the five non-top-3 qualifiers (Aurora,
    FURIA, BetBoom, 9z, G2) are assigned small pre-event longshot futures (~1-2.5%).  [ESTIMATED]
  - Stage-3 form update (mild, judgment): 3-0 finishers x1.20, 3-1 x1.00, 3-2 x0.85, then
    renormalize to 1.0.  [JUDGMENT]
Re-run with live futures the moment a provider is reachable — the fit then supersedes this prior.

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

# Pre-event winner futures over the 8 qualifiers, by TEAM NAME (renormalized later). The top three
# are the committed real Polymarket numbers; the five longshots are [ESTIMATED] pre-event futures.
_PREEVENT_FUTURES: dict[str, float] = {
    "Vitality": 0.50,
    "Spirit": 0.20,
    "Falcons": 0.09,
    "Aurora": 0.025,
    "FURIA": 0.025,
    "G2": 0.020,
    "BetBoom": 0.015,
    "9z": 0.010,
}
# Stage-3 finish per team (from the official posted results), driving the form multiplier.
_STAGE3_RECORD: dict[str, str] = {
    "Spirit": "3-0", "FURIA": "3-0",
    "Aurora": "3-1", "Falcons": "3-1", "Vitality": "3-1",
    "BetBoom": "3-2", "9z": "3-2", "G2": "3-2",
}
_FORM_MULT = {"3-0": 1.20, "3-1": 1.00, "3-2": 0.85}


def build_champion_target(teams) -> dict[int, float]:
    """The documented champion target by ENGINE ID: pre-event futures x Stage-3 form, renormalized."""
    id_of = {t.name: t.id for t in teams}
    raw = {
        name: _PREEVENT_FUTURES[name] * _FORM_MULT[_STAGE3_RECORD[name]]
        for name in _PREEVENT_FUTURES
    }
    total = sum(raw.values())
    return {id_of[name]: v / total for name, v in raw.items()}


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
