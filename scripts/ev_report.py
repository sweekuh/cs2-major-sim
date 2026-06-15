"""End-to-end EV report: your sim's fair value vs current Kalshi World Cup prices, saved to disk.

The "find EV" leg of the operating loop (docs/WORLDCUP.md §7), wired for live use and persistence:

  1. build the Elo-prior goals model (host advantage for Mexico/USA/Canada) and run the tournament
     Monte Carlo — one run prices every futures market;
  2. read the CURRENT betting options from Kalshi (keyless market data by default; signs the read
     with your API key if ``--signed-reads`` and credentials are present);
  3. map each market to its model probability and cost the edge net of the EXACT Kalshi fee +
     half-spread (``monitor.pipeline.scan`` -> ``monitor.edge``);
  4. size each +EV signal with fractional Kelly — against your REAL Kalshi balance when
     ``--use-balance`` and the API key is configured, else a flat ``--bankroll``;
  5. print the ranked table AND write ``data/ev_report.json`` (+ ``.md``) for later review / CLV.

READ-ONLY: it identifies bets, it never places them (execution is gated behind [Q-LEGAL]).

Credentials (optional, only needed for ``--use-balance`` / ``--signed-reads``): set
``KALSHI_API_KEY_ID`` (the owner's ``Kalshi`` env var is also accepted) and the RSA private key via
``KALSHI_PRIVATE_KEY`` (inline PEM) or ``KALSHI_PRIVATE_KEY_PATH`` (a file). See .env.example.

Run:
    uv run python -m scripts.ev_report                      # live keyless, flat bankroll
    uv run python -m scripts.ev_report --use-balance        # size against real Kalshi balance
    uv run python -m scripts.ev_report --fixture data/...   # offline, against a recorded markets file
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.soccer.dixon_coles import strengths_from_elo
from engine.soccer.teams import groups as group_by_letter
from engine.soccer.teams import host_ids, load_teams
from engine.soccer.tournament import run_tournament
from monitor.edge import stake_row
from monitor.pipeline import scan
from monitor.report import build_report, write_report
from odds.kalshi import KalshiWCProvider
from odds.kalshi_auth import KalshiClient

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_TICKERS = _DATA / "kalshi_wc_tickers.json"
_DEFAULT_SERIES = ["KXMENWORLDCUP", "KXWCGROUPWIN", "KXWCGROUPQUAL"]


def _series_tickers() -> list[str]:
    try:
        return list(json.loads(_TICKERS.read_text())["series"].keys())
    except (OSError, ValueError, KeyError):
        return list(_DEFAULT_SERIES)


def _states_from_fixture(path: str):
    """Parse a recorded Kalshi markets file (offline mode) into market states. Fail-soft to []."""
    return KalshiWCProvider().get_states(path)


def _states_live(client: KalshiClient, series: list[str], *, signed_reads: bool):
    """Fetch open Kalshi WC markets (keyless by default; signed iff asked + keyed). Fail-soft to []."""
    raw = client.fetch_market_dicts(series, status="open", signed=signed_reads)
    return KalshiWCProvider().get_states({"markets": raw})


def _enrich_rows(signals, states, *, bankroll: float, fraction: float) -> list[dict]:
    """Flatten signals to display/report rows, joining the team + title from the matching state."""
    state_by_ticker = {s.ticker: s for s in states}
    rows: list[dict] = []
    for sig in signals:
        row = stake_row(sig, bankroll=bankroll, fraction=fraction)
        st = state_by_ticker.get(sig.ticker)
        if st is not None:
            row["team"] = st.yes_sub_title
            row["title"] = st.title
        rows.append(row)
    return rows


def main(*, n_sims: int = 20_000, seed: int = 0, threshold: float = 0.03, bankroll: float = 1000.0,
         home_adv: float = 0.3, fraction: float = 0.25, maker: bool = False, use_balance: bool = False,
         signed_reads: bool = False, fixture: str | None = None,
         out_json: str | None = None, out_md: str | None = None) -> dict:
    teams, _ = load_teams()
    groups = {g: [t.id for t in members] for g, members in group_by_letter(teams).items()}
    model = strengths_from_elo(teams, home_adv=home_adv)
    result = run_tournament(groups, model, n_sims, seed=seed, hosts=host_ids(teams))

    client = KalshiClient.from_env()
    authed = client.authenticated

    # 2. current betting options — recorded fixture (offline) or live Kalshi.
    if fixture:
        states = _states_from_fixture(fixture)
        source = f"fixture:{Path(fixture).name}"
    else:
        states = _states_live(client, _series_tickers(), signed_reads=signed_reads and authed)
        source = "live:signed" if (signed_reads and authed) else "live:keyless"

    # 4. bankroll — real balance when keyed + asked, else the flat default.
    bankroll_used, balance_source = bankroll, "flat"
    if use_balance and authed:
        bal = client.get_balance()
        if bal is not None:
            bankroll_used, balance_source = bal, "kalshi_balance"

    # 3. map + cost + rank.
    signals, unmapped = scan(states, result, teams, threshold=threshold, maker=maker)
    rows = _enrich_rows(signals, states, bankroll=bankroll_used, fraction=fraction)

    meta = {
        "source": source,
        "authenticated": authed,
        "n_markets": len(states),
        "n_unmapped": len(unmapped),
        "threshold": threshold,
        "bankroll": round(bankroll_used, 2),
        "balance_source": balance_source,
        "kelly_fraction": fraction,
        "maker": maker,
        "n_sims": n_sims,
        "seed": seed,
        "home_adv": home_adv,
    }
    report = build_report(rows, meta=meta)

    jp = out_json or str(_DATA / "ev_report.json")
    mp = out_md or str(_DATA / "ev_report.md")
    write_report(report, json_path=jp, md_path=mp)

    _print_console(report, unmapped=len(unmapped), authed=authed, balance_source=balance_source,
                   json_path=jp)
    return report


def _print_console(report: dict, *, unmapped: int, authed: bool, balance_source: str,
                   json_path: str) -> None:
    meta = report["meta"]
    auth = "authenticated (key loaded)" if authed else "keyless (no API key / private key)"
    print(f"\nKalshi World Cup EV report — {meta['n_markets']} live markets, "
          f"{meta['n_edges']} edges > {meta['threshold']:.0%} net  [{auth}]")
    print(f"  source={meta['source']}  bankroll=${meta['bankroll']:.2f} ({balance_source})  "
          f"kelly={meta['kelly_fraction']}  n_sims={meta['n_sims']}\n")
    if meta["n_markets"] == 0:
        print("  No live Kalshi markets returned (no open markets, blocked egress host, or outage).")
        print("  If live: allowlist api.elections.kalshi.com in the env's network egress settings.\n")
    elif meta["n_edges"] == 0:
        print("  No +EV signals above threshold (efficient book, or edge inside fee+spread).\n")
    else:
        hdr = (f"{'ticker':<26}{'team':<16}{'type':<13}{'side':<5}{'model':>7}{'mid':>7}"
               f"{'net':>7}{'kelly':>7}{'stake':>9}")
        print(hdr)
        print("-" * len(hdr))
        for r in report["edges"]:
            print(f"{str(r.get('ticker',''))[:25]:<26}{str(r.get('team',''))[:15]:<16}"
                  f"{str(r.get('type',''))[:12]:<13}{r.get('side',''):<5}{r.get('model',0):>7.3f}"
                  f"{r.get('mid',0):>7.3f}{r.get('net_edge',0):>7.3f}{r.get('kelly',0):>7.3f}"
                  f"{r.get('stake',0):>9.2f}")
        print()
    print(f"  {unmapped} market(s) unmapped (e.g. per-match 1X2 — needs the match model).")
    print(f"  Saved: {json_path} (+ .md). Read-only, paper-only — CLV vs close is the truth oracle.\n")


def _cli() -> None:
    p = argparse.ArgumentParser(description="Kalshi World Cup EV report (read-only).")
    p.add_argument("--n-sims", type=int, default=20_000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--threshold", type=float, default=0.03, help="min net edge to report (default 3%)")
    p.add_argument("--bankroll", type=float, default=1000.0, help="flat bankroll if not --use-balance")
    p.add_argument("--home-adv", type=float, default=0.3)
    p.add_argument("--fraction", type=float, default=0.25, help="Kelly fraction (default quarter)")
    p.add_argument("--maker", action="store_true", help="cost with the maker fee (resting orders)")
    p.add_argument("--use-balance", action="store_true",
                   help="size against the real Kalshi balance (needs API key + private key)")
    p.add_argument("--signed-reads", action="store_true",
                   help="sign the market-data read too (default keyless — market data needs no key)")
    p.add_argument("--fixture", type=str, default=None,
                   help="path to a recorded Kalshi markets JSON (offline mode, no network)")
    p.add_argument("--out", type=str, default=None, help="output JSON path (default data/ev_report.json)")
    p.add_argument("--md", type=str, default=None, help="output markdown path (default data/ev_report.md)")
    a = p.parse_args()
    main(n_sims=a.n_sims, seed=a.seed, threshold=a.threshold, bankroll=a.bankroll,
         home_adv=a.home_adv, fraction=a.fraction, maker=a.maker, use_balance=a.use_balance,
         signed_reads=a.signed_reads, fixture=a.fixture, out_json=a.out, out_md=a.md)


if __name__ == "__main__":
    _cli()
