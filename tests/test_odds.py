"""Odds-core correctness guards (Phase 5, plan 05-01) — the pitfall-fatal ensemble math.

TDD Wave-0: this file imports the not-yet-existing ``odds.base`` / ``odds.oddspapi`` /
``odds.polymarket`` / ``odds.kalshi`` so it collects and runs RED (the Phase 1/3/4 convention),
then flips GREEN as the modules land.

Everything here is PURE / fixture-driven — there is NO network call. The providers parse the
RECORDED ``tests/fixtures/*_sample.json`` (handcrafted to the documented provider shapes;
field names are ``[ASSUMED — verify once Cologne markets post]`` per 05-RESEARCH A2-A5, and
reconciled at the 05-03 live-verify checkpoint).

CRITICAL design constraint (CLAUDE.md + 05-RESEARCH D1/DX-01): ``httpx`` must stay OUT of the
import path. The pure ``parse`` path the fixtures exercise must NOT import httpx, so this file
collects and runs even with NO httpx installed. (httpx is lazy-imported inside the live-fetch
method only.)

The load-bearing facts these tests pin (getting any wrong silently corrupts the thin-liquidity
matches that matter most):
  - De-vig ROUTES on ``vig_type``: ``devig_fixed_two_way`` for OddsPapi fixed odds;
    ``normalize_market_price`` for the prediction markets — a market price is NEVER two-way
    de-vigged (Pitfall 8).
  - The OddsPapi soft-book bundle is pre-pooled to ONE Pinnacle-anchored opinion BEFORE
    ``pool()`` sees it, so ``pool()`` never headcounts the soft books (Pitfall 7).
  - ``pool()`` is a liquidity/originate-weighted log-opinion pool: agreement -> var≈0,
    disagreement -> var>0, a single source -> var≈0 (PROB-05).
  - Polymarket + Kalshi are KEYLESS public reads, so a no-key pool still has 2 sources
    (the new fail-soft fact, D3/ODDS-08).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.teams import load_teams

# Imports of the not-yet-existing odds core — these make the file collect RED in Wave-0.
from odds.base import (
    BlendedProb,
    OddsQuote,
    devig_fixed_two_way,
    normalize_market_price,
    pool,
)
from odds.kalshi import KalshiProvider
from odds.oddspapi import OddsPapiProvider
from odds.polymarket import PolymarketProvider

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def teams():
    return load_teams()


# Engine ids for the fixture matchup: GamerLegion is seed/id 1, NRG is seed/id 9.
# sorted -> match key (1, 9); p_a_raw is P(lower-id team == GamerLegion wins the series).
_GL_ID = 1
_NRG_ID = 9
_EXPECTED_MATCH = (1, 9)


# --------------------------------------------------------------------------------------
# De-vig routing (ODDS-02, Pitfall 8)
# --------------------------------------------------------------------------------------


def test_devig_fixed():
    """OddsPapi fixed-odds two-way de-vig: 1.5 / 2.5 -> 0.625 (HANDOFF §5, ODDS-02)."""
    p = devig_fixed_two_way(1.5, 2.5)
    assert p == pytest.approx(0.625)
    # Equals the explicit overround removal (1/o_a)/(1/o_a + 1/o_b).
    assert p == pytest.approx((1 / 1.5) / (1 / 1.5 + 1 / 2.5))


def test_market_price_not_devigged():
    """A Polymarket/Kalshi price is normalized (spread/fee only), NEVER two-way de-vigged.

    normalize_market_price(0.71) stays ≈0.71; it must DIFFER from the (wrong) two-way
    de-vig of (0.71, 0.29), proving a market price is never run through the fixed-odds
    overround removal (Pitfall 8). Also assert the (eps, 1-eps) clamp off exactly 0/1.
    """
    p = normalize_market_price(0.71)
    assert p == pytest.approx(0.71, abs=1e-6)
    # The two paths MUST differ — applying the two-way de-vig to a price ≈ prob is corruption.
    wrong = devig_fixed_two_way(0.71, 0.29)
    assert p != pytest.approx(wrong)
    # Clamp: degenerate 0.0 / 1.0 land strictly inside (0, 1), never exactly on the boundary.
    lo = normalize_market_price(0.0)
    hi = normalize_market_price(1.0)
    assert 0.0 < lo < 1.0
    assert 0.0 < hi < 1.0


# --------------------------------------------------------------------------------------
# Log-opinion pool (ODDS-03, PROB-05)
# --------------------------------------------------------------------------------------


def _quote(p, *, originate=1.0, liquidity=10.0, vig_type="market", bo3=False):
    return OddsQuote(
        provider="test",
        match=_EXPECTED_MATCH,
        p_a_raw=p,
        vig_type=vig_type,
        bo3=bo3,
        liquidity=liquidity,
        originate=originate,
        ts=0.0,
    )


def test_pool_agreeing_low_var():
    """Three agreeing sources (all p≈0.70, equal weight) -> p≈0.70, var≈0, n_sources==3.

    Agreement -> near-zero epistemic spread; the band collapses to the inner Wilson (PROB-05).
    """
    quotes = [_quote(0.70), _quote(0.70), _quote(0.70)]
    blended = pool(quotes)
    assert isinstance(blended, BlendedProb)
    assert blended.p == pytest.approx(0.70, abs=1e-9)
    assert blended.var < 1e-4
    assert blended.n_sources == 3


def test_pool_disagreeing_high_var():
    """Two disagreeing sources (0.45 and 0.75) -> var strictly > the agreeing case, p between.

    Hand-check: equal weights -> zbar = mean of logit(0.45)=-0.2007 and logit(0.75)=1.0986,
    so zbar≈0.4490, p=sigmoid(0.4490)≈0.610 (between 0.45 and 0.75). logit_var > 0 -> var > 0,
    and strictly larger than the agreeing (all-equal) case whose logit_var is 0.
    """
    agreeing = pool([_quote(0.70), _quote(0.70)])
    disagreeing = pool([_quote(0.45), _quote(0.75)])
    assert disagreeing.var > agreeing.var
    assert 0.45 < disagreeing.p < 0.75
    assert disagreeing.n_sources == 2


# --------------------------------------------------------------------------------------
# OddsPapi soft-book bundle pre-pool — the headcount guard (ODDS-03, Pitfall 7)
# --------------------------------------------------------------------------------------


def test_softbook_bundle_one_opinion(teams):
    """[CRITICAL] The 4-book OddsPapi bundle collapses to EXACTLY ONE Pinnacle-anchored quote.

    The fixture has Pinnacle + 3 soft books for one match. get_quotes must emit ONE OddsQuote
    for that match (the within-bundle pre-pool), NOT one per book — otherwise the soft books
    headcount-drown the two independent markets (Pitfall 7). The surviving quote must carry a
    HIGH originate (the sharp-originator weight), proving it is the Pinnacle-anchored opinion.
    """
    raw = _load("oddspapi_sample.json")
    quotes = OddsPapiProvider().get_quotes(raw, teams=teams)
    for_match = [q for q in quotes if q.match == _EXPECTED_MATCH]
    assert len(for_match) == 1, "the soft-book bundle must pre-pool to ONE opinion (Pitfall 7)"
    q = for_match[0]
    # Pinnacle is the sharp originator -> the surviving bundle opinion carries the high originate.
    assert q.originate >= 1.0


# --------------------------------------------------------------------------------------
# Provider fixture parse (ODDS-05)
# --------------------------------------------------------------------------------------


def test_oddspapi_parse_fixture(teams):
    """The single OddsPapi quote is fixed-vig, de-vigged near the Pinnacle book, engine-id keyed.

    Pinnacle book 1.50/2.50 hand-de-vigs to 0.625; the bundle pre-pool (Pinnacle weighted
    highest, soft books 0.608..0.633) lands p_a_raw close to that, strictly in (0,1). match is
    the sorted engine-id tuple (1, 9); bo3 follows the fixture (False).
    """
    raw = _load("oddspapi_sample.json")
    quotes = OddsPapiProvider().get_quotes(raw, teams=teams)
    [q] = [x for x in quotes if x.match == _EXPECTED_MATCH]
    assert q.vig_type == "fixed"
    assert 0.0 < q.p_a_raw < 1.0
    # Close to the Pinnacle anchor de-vig (0.625), within the soft-book spread.
    assert q.p_a_raw == pytest.approx(0.625, abs=0.05)
    assert q.match == _EXPECTED_MATCH
    assert q.bo3 is False


def test_polymarket_parse_fixture(teams):
    """Polymarket parses to a vig_type==market quote with p_a_raw ≈ outcomePrice (no de-vig)."""
    raw = _load("polymarket_sample.json")
    quotes = PolymarketProvider().get_quotes(raw, teams=teams)
    [q] = [x for x in quotes if x.match == _EXPECTED_MATCH]
    assert q.vig_type == "market"
    # GamerLegion (lower id) priced 0.71 -> normalized ≈ 0.71, NOT two-way de-vigged.
    assert q.p_a_raw == pytest.approx(0.71, abs=1e-3)
    assert q.match == _EXPECTED_MATCH


def test_kalshi_parse_fixture(teams):
    """Kalshi parses yes_bid_dollars/yes_ask_dollars -> p_a_raw ≈ mid, vig_type==market.

    Two complementary markets per event_ticker dedupe to ONE opinion. The GamerLegion side
    quotes yes_bid_dollars 0.67 / yes_ask_dollars 0.69 -> mid 0.68 for GamerLegion (lower id).
    """
    raw = _load("kalshi_sample.json")
    quotes = KalshiProvider().get_quotes(raw, teams=teams)
    [q] = [x for x in quotes if x.match == _EXPECTED_MATCH]
    assert q.vig_type == "market"
    assert q.p_a_raw == pytest.approx(0.68, abs=1e-3)
    assert q.match == _EXPECTED_MATCH


def test_kalshi_empty_market_yields_empty(teams):
    """The empty markets:[] variant -> get_quotes(...) == [] (fail-soft, ODDS-05, not an error)."""
    raw = _load("kalshi_sample.json")["empty"]
    quotes = KalshiProvider().get_quotes(raw, teams=teams)
    assert quotes == []


# --------------------------------------------------------------------------------------
# Keyless 2-source pool — the new fail-soft fact (D3/ODDS-08)
# --------------------------------------------------------------------------------------


def test_keyless_two_source_pool(teams, monkeypatch):
    """With NO ODDSPAPI_KEY the Polymarket + Kalshi (keyless) quotes still pool to 2 sources.

    The key only unlocks the OddsPapi/Pinnacle anchor; the two prediction markets are keyless
    public reads, so a no-key fetch still populates a 2-source BlendedProb (ODDS-08 fail-soft).
    """
    monkeypatch.delenv("ODDSPAPI_KEY", raising=False)
    poly = PolymarketProvider().get_quotes(_load("polymarket_sample.json"), teams=teams)
    kalshi = KalshiProvider().get_quotes(_load("kalshi_sample.json"), teams=teams)
    quotes = [q for q in (*poly, *kalshi) if q.match == _EXPECTED_MATCH]
    blended = pool(quotes)
    assert blended.n_sources == 2
    assert 0.0 < blended.p < 1.0
