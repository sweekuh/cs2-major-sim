"""Pure odds-ensemble core for the Cologne 2026 Swiss simulator (Phase 5).

Package layout:
  base.py       — OddsQuote / BlendedProb dataclasses, OddsProvider Protocol, de-vig
                  helpers (routed by vig_type), and pool() (originate/liquidity-weighted
                  log-opinion pool with cross-source epistemic variance). PURE numpy.
  oddspapi.py   — OddsPapiProvider: fixed-odds de-vig + soft-book bundle pre-pool to ONE
                  Pinnacle-anchored opinion (Pitfall 7).
  polymarket.py — PolymarketProvider: market-price normalize (keyless Gamma read).
  kalshi.py     — KalshiProvider: yes-mid market-price normalize (keyless trade-api read).

INVARIANT (D1/DX-01): httpx/python-dotenv are imported ONLY inside the providers'
live-fetch methods (lazy import in the get_quotes network branch) — never at module top,
so the fixture-parse path collects and runs with NO httpx installed, and nothing here is
reachable from the app import path.
"""
