"""One-off (Stage-3 window, June 9-15): the hourly odds-refresh pipeline the Windows task runs.

Three steps, each fail-soft to the previous state of data/odds_cache.json:

  1. ``scripts.fetch_odds.main(stage_id="stage3")`` — live KXCS2GAME R1 series prices
     (bo3-stamped; the fetch rewrites the cache, so steps 2-3 re-derive what it drops).
  2. Pull the live Kalshi KXCS2QUALIFIERS-26IEMCOLPO playoff-qualify yes-mids, resolve
     them to stage-3 engine ids, renormalize to sum EXACTLY ``QUALIFY_SLOTS`` (8) by a
     constant logit shift, and write the operator ``"qualify"`` block. The logit shift —
     not the multiplicative renorm inside fit_qualify_ratings — is deliberate: these thin
     books' mids sum well under 8 (observed 7.31 on 2026-06-09), and a multiplicative
     scale pushes the near-1 favorites past 1 into the clamp (Vitality 0.935 -> ~1.0
     target -> a degenerate 97% P(3-0) forecast). A logit shift preserves ordering and
     keeps every target strictly inside (0, 1). With the supplied targets already summing
     to 8, the engine's own renorm is a no-op.
  3. ``scripts.fit_qualify.main(stage_id="stage3")`` — the rounds-2-5 calibration the app
     prefers over the R1 back-solve (QFIT-03).

If step 2 or 3 fails, the cache is left as a valid R1-only stage-3 fetch (the app falls
back to the R1 back-solve — degraded, never wrong-stage, never a crash).

Run:  uv run python -m scripts.refresh_stage3_odds
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

log = logging.getLogger("scripts.refresh_stage3_odds")

CACHE = Path("data/odds_cache.json")
QUALIFY_SERIES = "KXCS2QUALIFIERS"
QUALIFY_EVENT_FRAGMENT = "26IEMCOLPO"  # "...qualify for the playoffs at 2026 IEM Cologne"
QUALIFY_SLOTS = 8


def _logit_renorm(raw: dict[str, float], target_sum: float) -> dict[str, float]:
    """Shift all logits by one constant so the probs sum to ``target_sum`` (bisection)."""
    logits = {k: math.log(p / (1.0 - p)) for k, p in raw.items()}

    def total(c: float) -> float:
        return sum(1.0 / (1.0 + math.exp(-(l + c))) for l in logits.values())

    lo, hi = -5.0, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if total(mid) < target_sum:
            lo = mid
        else:
            hi = mid
    c = (lo + hi) / 2.0
    return {k: round(1.0 / (1.0 + math.exp(-(l + c))), 4) for k, l in logits.items()}


def _write_qualify_block() -> None:
    """Fetch live playoff-qualify mids, join to stage-3 ids, renorm, write into the cache."""
    import httpx

    from engine.teams import load_stage
    from odds._match import build_name_to_id, resolve_id
    from scripts.fetch_odds import _path_for_stage

    teams, _ = load_stage(_path_for_stage("stage3"))
    name_to_id = build_name_to_id(teams)

    r = httpx.get(
        "https://api.elections.kalshi.com/trade-api/v2/markets",
        params={"series_ticker": QUALIFY_SERIES, "status": "open", "limit": 200},
        timeout=20,
    )
    r.raise_for_status()
    mks = [m for m in r.json().get("markets", []) if QUALIFY_EVENT_FRAGMENT in (m.get("ticker") or "")]

    raw: dict[str, float] = {}
    for mk in mks:
        tid = resolve_id(mk.get("yes_sub_title") or "", name_to_id)
        if tid is None:  # the eliminated Stage-1/2 teams' markets — expected, not an error
            continue
        bid = float(mk.get("yes_bid_dollars") or 0.0)
        ask = float(mk.get("yes_ask_dollars") or 0.0)
        mid = (bid + ask) / 2.0
        if not (0.0 < mid < 1.0):  # a 0.00/0.00 or settled book can't carry a logit
            mid = min(max(mid, 0.005), 0.995)
        raw[str(tid)] = mid

    if len(raw) != len(teams):
        raise ValueError(f"resolved {len(raw)} of {len(teams)} stage-3 qualify markets")

    qualify = _logit_renorm(raw, float(QUALIFY_SLOTS))
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    cache["qualify"] = qualify
    cache["_meta"]["qualify_note"] = (
        f"Kalshi {QUALIFY_SERIES}-{QUALIFY_EVENT_FRAGMENT} yes-mids (raw sum "
        f"{sum(raw.values()):.3f}) logit-renormalized to sum exactly {QUALIFY_SLOTS} before "
        "the fit, so no near-1 target saturates fit_qualify_ratings' renorm clamp."
    )
    CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    log.info("qualify block written: %d targets, raw sum %.3f", len(qualify), sum(raw.values()))


def main() -> None:
    from scripts.fetch_odds import main as fetch_main

    fetch_main(stage_id="stage3")  # step 1 — its own fail-soft leaves a valid (maybe empty) cache

    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    if not cache.get("blended"):
        log.warning("no blended R1 markets fetched; skipping qualify fit (rating-only cache)")
        return

    try:
        _write_qualify_block()  # step 2
    except Exception as exc:  # noqa: BLE001 — fail-soft to the R1-only cache
        log.warning("qualify pull failed (%s); cache stays R1-only", exc)
        return

    try:
        from scripts.fit_qualify import main as fit_main

        fit_main(stage_id="stage3")  # step 3
    except Exception as exc:  # noqa: BLE001 — fail-soft: app falls back to the R1 back-solve
        log.warning("qualify fit failed (%s); cache stays R1-only", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
