"""sqlite signal log + CLV vs Pinnacle close (PRD R6, the project's truth oracle).

CLV (closing-line value) is the instrument that tells us empirically whether the fair value has
alpha: if the price we flagged consistently beats the sharp closing line, the model has edge;
if mean CLV is not significantly > 0, we stop or rebuild before risking real money. So EVERY
emitted signal is persisted with a timestamped fair value and Kalshi price, and after the
referenced market settles we join the Pinnacle close and compute CLV.

Storage is sqlite: a single-process, single-writer personal monitor has no concurrent writers
and no network-DB needs, so Postgres buys nothing and adds ops burden. The DB file is portable
and trivially backed up. All inputs are logged raw so any signal is reproducible after the fact.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    ticker        TEXT    NOT NULL,
    market_type   TEXT    NOT NULL,
    side          TEXT    NOT NULL,            -- 'yes' or 'no' (which contract we'd buy)
    fair_value    REAL    NOT NULL,
    fair_source   TEXT    NOT NULL,
    kalshi_mid    REAL    NOT NULL,
    spread        REAL    NOT NULL,
    depth         REAL    NOT NULL,
    net_edge      REAL    NOT NULL,
    model_conf    REAL    NOT NULL,
    alerted       INTEGER NOT NULL DEFAULT 0,
    pinnacle_close REAL,                       -- filled in after settlement
    clv           REAL                         -- filled in after settlement
);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
"""


@dataclass(frozen=True)
class Signal:
    """One emitted edge signal (PRD R5/R6 payload). ``ts`` defaults to wall-clock at creation."""

    ticker: str
    market_type: str
    side: str
    fair_value: float
    fair_source: str
    kalshi_mid: float
    spread: float
    depth: float
    net_edge: float
    model_conf: float
    alerted: bool = False
    ts: float = 0.0


def compute_clv(entry_price: float, close_price: float, side: str) -> float:
    """CLV as a percentage: how much better our flagged price was than the sharp close.

    For a YES buy at ``entry_price`` that later closes at ``close_price``, beating the close means
    the fair probability rose toward (or past) our entry — we got the contract cheaper than the
    closing line implies: ``(close_price / entry_price - 1) * 100``. For a NO buy the relevant
    price is ``1 - price``, so the sign flips appropriately. Positive CLV = we were on the right
    side of the closing line. Raises on a non-positive entry price (cannot divide).
    """
    if side == "no":
        entry_price = 1.0 - entry_price
        close_price = 1.0 - close_price
    if entry_price <= 0.0:
        raise ValueError(f"entry_price must be positive to compute CLV, got {entry_price!r}")
    return (close_price / entry_price - 1.0) * 100.0


class SignalLog:
    """Append-only signal store with post-settlement CLV backfill. Pass ``:memory:`` for tests."""

    def __init__(self, path: str | Path = "wc_signals.db"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, sig: Signal) -> int:
        """Persist a signal; returns its row id. Stamps wall-clock ts when the signal omits one."""
        ts = sig.ts or time.time()
        cur = self._conn.execute(
            """INSERT INTO signals
               (ts, ticker, market_type, side, fair_value, fair_source, kalshi_mid,
                spread, depth, net_edge, model_conf, alerted)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ts, sig.ticker, sig.market_type, sig.side, sig.fair_value, sig.fair_source,
             sig.kalshi_mid, sig.spread, sig.depth, sig.net_edge, sig.model_conf,
             int(sig.alerted)),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def settle(self, signal_id: int, pinnacle_close: float) -> float:
        """Backfill the Pinnacle close for a signal and compute+store its CLV; returns the CLV."""
        row = self._conn.execute(
            "SELECT kalshi_mid, side FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no signal with id {signal_id}")
        clv = compute_clv(row["kalshi_mid"], pinnacle_close, row["side"])
        self._conn.execute(
            "UPDATE signals SET pinnacle_close = ?, clv = ? WHERE id = ?",
            (pinnacle_close, clv, signal_id),
        )
        self._conn.commit()
        return clv

    def mean_clv(self) -> tuple[float, int]:
        """Mean CLV over all settled signals and the settled count (PRD: positive+significant=alpha)."""
        row = self._conn.execute(
            "SELECT AVG(clv) AS m, COUNT(clv) AS n FROM signals WHERE clv IS NOT NULL"
        ).fetchone()
        n = int(row["n"] or 0)
        return (float(row["m"]) if n else 0.0, n)

    def all_signals(self) -> list[sqlite3.Row]:
        """Every logged signal, newest first (for inspection / CLV analysis)."""
        return list(self._conn.execute("SELECT * FROM signals ORDER BY ts DESC").fetchall())

    def close(self) -> None:
        self._conn.close()
