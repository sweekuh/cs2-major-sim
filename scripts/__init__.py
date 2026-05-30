"""Operational scripts for swiss-mc (Phase 5).

The ONLY package that imports httpx / python-dotenv at the script level — ``scripts.fetch_odds``
is the single entry both the UI "fetch now" button (lazy-imported inside the click handler) AND
a future v2 cron call (``python -m scripts.fetch_odds``) share. It writes the read-only
``data/odds_cache.json`` the app reads back via ``ui/odds_loader.py``; nothing here is reachable
from the app/ui import path (DX-01, Pitfall 11).
"""
