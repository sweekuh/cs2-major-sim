"""Read published match schedules and Kalshi books; freeze one paper entry per match."""

import gzip
import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

from .model import HERE, SIZE, D, ceiling, fit, forecast, name, walk

BASE = "https://api.elections.kalshi.com/trade-api/v2"
MATCHES = "https://api.bo3.gg/api/v1/matches"
SERIES = ("KXCS2GAME", "KXCS2GAMES", "KXCSGOGAME")
TOURNAMENTS = (6269, 6268, 4226)
LEDGER = HERE / "paper.sqlite3"


def now():
    return datetime.now(UTC)


def get(client, url, **params):
    r = client.get(url, params=params)
    r.raise_for_status()
    return r.json()


def schedule(client):
    games = {}
    for event in TOURNAMENTS:
        offset = 0
        while True:
            d = get(
                client,
                MATCHES,
                **{
                    "filter[matches.tournament_id][eq]": event,
                    "with": "teams",
                    "sort": "start_date",
                    "page[limit]": 100,
                    "page[offset]": offset,
                },
            )
            for m in d["results"]:
                if m["tournament_id"] != event:
                    raise ValueError("Unexpected tournament in fixture feed")
                if not (m.get("team1") and m.get("team2")):
                    continue
                sides = [name(m[k]["name"]) for k in ("team1", "team2")]
                winner = next(
                    (
                        s
                        for s, k in zip(sides, ("team1_id", "team2_id"))
                        if m.get("winner_team_id") == m[k]
                    ),
                    None,
                )
                games[str(m["id"])] = {
                    "teams": sides,
                    "bo": m["bo_type"],
                    "start": m["start_date"],
                    "status": m["status"],
                    "score": [m["team1_score"], m["team2_score"]],
                    "winner": winner,
                    "event": event,
                    "round": m["round_id"],
                    "url": "https://bo3.gg/matches/" + m["slug"],
                }
            offset += len(d["results"])
            if offset >= d["total"]["count"]:
                break
            if not d["results"]:
                raise ValueError("Incomplete schedule page")
    return games


def catalog(client):
    listings, series_info, candidates = {}, {}, []
    for series in SERIES:
        info = get(client, BASE + "/series/" + series)["series"]
        series_info[series] = {
            k: info[k]
            for k in ("fee_type", "fee_multiplier", "contract_terms_url", "settlement_sources")
        }
        cursor = None
        listings[series] = []
        while True:
            params = {"series_ticker": series, "status": "open", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            page = get(client, BASE + "/markets", **params)
            for m in page["markets"]:
                listings[series].append(m["ticker"])
                if (
                    "singapore"
                    in (
                        m["rules_primary"]
                        + " "
                        + m["title"]
                        + " "
                        + (m.get("rules_secondary") or "")
                    ).casefold()
                ):
                    candidates.append((series, m))
            cursor = page.get("cursor")
            if not cursor:
                break
    return listings, series_info, candidates


def scheduled_time(m):
    # GAME tickers encode originally scheduled US Eastern kickoff. November–December is EST.
    part = m["event_ticker"].split("-")[-1]
    stamp = re.match(r"(\d\d[A-Z]{3}\d{6})", part)
    if stamp:
        return datetime.strptime(stamp[1], "%y%b%d%H%M").replace(
            tzinfo=timezone(timedelta(hours=-5))
        )
    return None


def belongs(m, g, *, canonicalize=name):
    teams = g["teams"]
    yes = canonicalize(m.get("yes_sub_title") or "")
    subject = re.match(r"If (.+?) wins the ", m["rules_primary"], re.IGNORECASE)
    if yes not in teams or not subject or canonicalize(subject[1]) != yes:
        return False
    time = scheduled_time(m)
    if time is None or abs(time - datetime.fromisoformat(g["start"])) > timedelta(minutes=90):
        return False
    # The two contract competitors must be independently identifiable in the event wording.
    match = re.search(r":\s*(.+?)\s+vs\.?\s+(.+?)\s+CS2 match", m["rules_primary"], re.IGNORECASE)
    if not match:
        return False
    return {canonicalize(match[1]), canonicalize(match[2])} == set(teams)


def inspect_book(m, series_info, data, fair, teams):
    result = []
    if (
        m["status"] != "active"
        or m["market_type"] != "binary"
        or D(m["notional_value_dollars"]) != 1
    ):
        return result
    if series_info["fee_type"] not in ("quadratic", "quadratic_with_maker_fees"):
        return result
    mult = D(str(series_info["fee_multiplier"]))
    if not (m.get("rules_primary") and m.get("rules_secondary")):
        return result
    yes = name(m["yes_sub_title"])
    sides = [yes, next(n for n in teams if n != yes)]
    book = data["orderbook_fp"]
    for side, team, opposite, same in (
        ("yes", sides[0], "no_dollars", "yes_dollars"),
        ("no", sides[1], "yes_dollars", "no_dollars"),
    ):
        asks = book.get(opposite) or []
        bids = book.get(same) or []
        execution = walk(asks, mult)
        opposite_execution = walk(bids, mult)
        available = sum(D(q) for _, q in asks)
        margin = None
        if asks and bids:
            margin = 100 * (1 - max(float(p) for p, _ in asks) - max(float(p) for p, _ in bids))
        entry = {
            "ticker": m["ticker"],
            "side": side,
            "team": team,
            "available": float(available),
            "spread_c": margin,
            "fee_multiplier": float(mult),
            "execution": execution,
            "liquid_mid_c": None,
        }
        if execution:
            all_in = execution["debit_usd"] * 100 / SIZE
            entry.update(
                net_c=fair[team]["p"] * 100 - all_in,
                conservative_net_c=fair[team]["low"] * 100 - all_in,
            )
        if execution and opposite_execution and margin is not None and -1e-8 <= margin <= 5.000001:
            bid10 = 100 - opposite_execution["ask_c"]
            if execution["ask_c"] - bid10 <= 5.000001:
                entry["liquid_mid_c"] = (execution["ask_c"] + bid10) / 2
        result.append(entry)
    return result


def decide(g, fit_data, matched, infos, books, watch_multiplier):
    a, b = g["teams"]
    pa = forecast(a, b, g["bo"], fit_data)
    fair = {a: pa, b: {"p": 1 - pa["p"], "low": 1 - pa["high"], "high": 1 - pa["low"]}}
    limits = {n: ceiling(f["low"], watch_multiplier) for n, f in fair.items()}
    options = []
    for series, m in matched:
        options.extend(inspect_book(m, infos[series], books[m["ticker"]]["book"], fair, g["teams"]))
    qualified = [
        x for x in options if x["liquid_mid_c"] is not None and x["conservative_net_c"] > 1e-8
    ]
    executable = [x for x in options if x["execution"]]
    best = max(qualified or executable, key=lambda x: x["conservative_net_c"], default=None)
    reason = (
        "positive under stressed fair value"
        if qualified
        else "unlisted"
        if not matched
        else "insufficient depth or unverified contract"
        if not executable
        else "book too wide or lacks two-sided depth"
        if best["liquid_mid_c"] is None
        else "price exceeds conservative ceiling"
    )
    return dict(
        **g,
        fair=fair,
        limits_c=limits,
        options=options,
        best=best,
        decision="TAKE" if qualified else "PASS",
        reason=reason,
    )


def initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS scans(at TEXT PRIMARY KEY, payload BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS first_forecasts(match TEXT PRIMARY KEY, at TEXT, row TEXT);
        CREATE TABLE IF NOT EXISTS entries(match TEXT PRIMARY KEY, at TEXT, row TEXT);
        CREATE TABLE IF NOT EXISTS closes(match TEXT, ticker TEXT, side TEXT, at TEXT, mid REAL,
                                          PRIMARY KEY(match,ticker,side));
        CREATE TABLE IF NOT EXISTS grades(match TEXT PRIMARY KEY, at TEXT, raw TEXT);
    """)


def pack(obj):
    return gzip.compress(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
    )


def roster_check(client):
    roster_file = json.loads((HERE / "rosters.json").read_text(encoding="utf8"))
    # A changed organizer sheet needs a lineup review before the next paper entry.
    roster_hash = hashlib.sha256(get(client, roster_file["source"])["content"].encode()).hexdigest()
    return roster_hash, roster_hash != roster_file["content_hash"]


def scan(db, client):
    games = schedule(client)
    listings, infos, markets = catalog(client)
    model = fit()
    books = {}
    rows = {}
    linked = set()
    for mid, g in games.items():
        if (
            g["status"] != "upcoming"
            or any(g["score"])
            or now() >= datetime.fromisoformat(g["start"])
        ):
            continue
        matched = [(series, m) for series, m in markets if belongs(m, g)]
        for _, m in matched:
            linked.add(m["ticker"])
            tick = m["ticker"]
            books[tick] = {
                "book": get(client, BASE + "/markets/" + tick + "/orderbook"),
                "at": now().isoformat(),
            }
        mult = D(str(infos[SERIES[0]]["fee_multiplier"]))
        tradable = [(series, m) for series, m in matched if now() < scheduled_time(m)]
        rows[mid] = decide(g, model, tradable, infos, books, mult)
        if matched and not tradable:
            rows[mid].update(decision="PASS", reason="original Kalshi kickoff passed")
    roster_hash, roster_changed = roster_check(client)
    # Refuse to record an entry from a long scan, a late book or a game that has begun.
    if books:
        recent = schedule(client)
        at = now()
        for mid, row in list(rows.items()):
            g = recent.get(mid)
            if (
                not g
                or g["status"] != "upcoming"
                or any(g["score"])
                or g["start"] != row["start"]
                or g["teams"] != row["teams"]
            ):
                del rows[mid]
            elif any(
                (at - datetime.fromisoformat(books[o["ticker"]]["at"])).total_seconds() > 30
                for o in row["options"]
            ):
                row.update(decision="PASS", reason="book snapshot older than 30 seconds")
    at = now()
    rows = {i: r for i, r in rows.items() if at < datetime.fromisoformat(r["start"])}
    cutoffs = {m["ticker"]: scheduled_time(m) for _, m in markets}
    for row in rows.values():
        if any(at >= cutoffs[o["ticker"]] for o in row["options"]):
            row.update(decision="PASS", reason="original Kalshi kickoff passed")
        if roster_changed:
            row.update(decision="PASS", reason="updated PGL roster sheet requires review")
        row["usable_close"] = not any(
            at >= cutoffs[o["ticker"]] or (at - datetime.fromisoformat(books[o["ticker"]]["at"])).total_seconds() > 30
            for o in row["options"]
        )
    timestamp = at.isoformat()
    unmatched = [m["ticker"] for _, m in markets if m["ticker"] not in linked]
    payload = {
        "at": timestamp,
        "model": model,
        "listed": listings,
        "series": infos,
        "contracts": [m for _, m in markets],
        "books": books,
        "games": games,
        "rows": rows,
        "unmatched": unmatched,
        "roster_changed": roster_changed,
        "roster_hash": roster_hash,
    }
    with db:
        db.execute("BEGIN IMMEDIATE")
        for mid, row in rows.items():
            blob = json.dumps(row)
            db.execute(
                "INSERT OR IGNORE INTO first_forecasts VALUES(?,?,?)", (mid, timestamp, blob)
            )
            previous = db.execute("SELECT at,row FROM entries WHERE match=?", (mid,)).fetchone()
            if previous:
                row["decision"] = "HOLD"
                row["reason"] = "entry previously frozen at " + previous[0]
                row["frozen_entry"] = json.loads(previous[1])["best"]
            elif row["decision"] == "TAKE":
                db.execute("INSERT INTO entries VALUES(?,?,?)", (mid, timestamp, blob))
            soon = (datetime.fromisoformat(row["start"]) - at).total_seconds() <= 1800
            if soon and row["usable_close"]:
                for opt in row["options"]:
                    if opt["liquid_mid_c"] is not None:
                        db.execute(
                            "INSERT OR REPLACE INTO closes VALUES(?,?,?,?,?)",
                            (mid, opt["ticker"], opt["side"], timestamp, opt["liquid_mid_c"]),
                        )
        db.execute("INSERT INTO scans VALUES(?,?)", (timestamp, pack(payload)))
    return payload


def grade(db, client):
    for mid, raw in db.execute(
        "SELECT match,row FROM entries WHERE match NOT IN (SELECT match FROM grades)"
    ).fetchall():
        opt = json.loads(raw)["best"]
        m = get(client, BASE + "/markets/" + opt["ticker"])["market"]
        if m["status"] not in ("finalized", "settled"):
            continue
        payout = m.get("settlement_value_dollars")
        if payout is None:
            payout = {"yes": "1", "no": "0"}.get(m.get("result"))
        if payout is None:
            continue
        v = D(str(payout))
        if not 0 <= v <= 1:
            raise ValueError("Invalid exchange settlement")
        if opt["side"] == "no":
            v = 1 - v
        pnl = float(v * SIZE - D(str(opt["execution"]["debit_usd"])))
        with db:
            db.execute(
                "INSERT OR IGNORE INTO grades VALUES(?,?,?)",
                (mid, now().isoformat(), json.dumps({"market": m, "pnl": pnl})),
            )


def rows_from(db, table):
    return {i: json.loads(row) for i, row in db.execute(f"SELECT match,row FROM {table}")}


def report(db, snap):
    first = rows_from(db, "first_forecasts")
    entries = rows_from(db, "entries")
    grades = {i: json.loads(raw) for i, raw in db.execute("SELECT match,raw FROM grades")}
    brier = []
    losses = []
    labels = []
    pnl = []
    clv = []
    for mid, row in first.items():
        g = snap["games"].get(mid)
        side = row["teams"][0]
        if (
            not g
            or g["status"] != "finished"
            or g["winner"] not in row["teams"]
            or set(g["teams"]) != set(row["teams"])
        ):
            continue
        p = row["fair"][side]["p"]
        y = int(side == g["winner"])
        if any(x == 0 for x in g["score"]) and max(g["score"]) == 0:
            continue
        brier.append((y - p) ** 2)
        losses.append(-np.log(p if y else 1 - p))
        labels.append((p, y))
    tickets = []
    settled_days = {}
    for mid, row in entries.items():
        opt = row["best"]
        close = db.execute(
            "SELECT at,mid FROM closes WHERE match=? AND ticker=? AND side=?",
            (mid, opt["ticker"], opt["side"]),
        ).fetchone()
        # A pre-start mark is final only once that match has begun.
        current = snap["games"].get(mid)
        if current is None or current["status"] == "upcoming":
            close = None
        if close:
            cutoff = datetime.fromisoformat(current["start"])
            if not cutoff - timedelta(minutes=30) <= datetime.fromisoformat(close[0]) < cutoff:
                close = None
        edge = close[1] - opt["execution"]["debit_usd"] * 100 / SIZE if close else None
        if edge is not None:
            clv.append(edge)
        profit = grades.get(mid, {}).get("pnl")
        if profit is not None:
            pnl.append(profit)
            day = row["start"][:10]
            settled_days.setdefault(day, []).append(profit)
        tickets.append(
            {
                "match": mid,
                "team": opt["team"],
                "ticker": opt["ticker"],
                "side": opt["side"],
                "entry": opt["execution"],
                "close_at": close[0] if close else None,
                "closing_mid_c": close[1] if close else None,
                "clv_net_c": edge,
                "settled_pnl": profit,
            }
        )
    bins = []
    for lower in range(0, 100, 10):
        vals = [(p, y) for p, y in labels if lower <= p * 100 < lower + 10]
        if vals:
            bins.append(
                {
                    "from_pct": lower,
                    "n": len(vals),
                    "mean_forecast": float(np.mean([p for p, _ in vals])),
                    "observed": float(np.mean([y for _, y in vals])),
                }
            )
    # A match-day block preserves dependence among same-day picks. Small samples stay unscored.
    profit_interval = None
    if len(settled_days) >= 5:
        days = list(settled_days.values())
        day_counts = np.array([len(values) for values in days])
        day_pnl = np.array([sum(values) for values in days])
        weights = np.random.default_rng(20261120).multinomial(
            len(days), np.ones(len(days)) / len(days), size=5000
        )
        profit_interval = list(
            np.quantile((weights @ day_pnl) / (weights @ day_counts), [0.025, 0.975])
        )
    missed = [
        mid for mid, g in snap["games"].items() if g["status"] == "finished" and mid not in first
    ]
    return {
        "unique_matches": len(first),
        "ever_taken": len(entries),
        "never_taken": len(first) - len(entries),
        "finished_without_pregame": missed,
        "settled_match_days": len(settled_days),
        "mean_pnl_per_entry_day_bootstrap95": profit_interval,
        "settled_entries": len(pnl),
        "realized_net_usd": round(sum(pnl), 4),
        "n_scored": len(losses),
        "brier": float(np.mean(brier)) if brier else None,
        "log_loss": float(np.mean(losses)) if losses else None,
        "calibration": bins,
        "clv_n": len(clv),
        "avg_clv_net_c": float(np.mean(clv)) if clv else None,
        "entries": tickets,
    }


def display(n):
    return {
        "Ninjas in Pyjamas": "NIP",
        "PARIVISION": "PVISION",
        "BC.Game": "GOSH",
        "BETBOOM": "BB TEAM",
        "1win": "The One",
    }.get(n, n)


def sheet(snap, stats):
    lines = [
        "# Singapore Major · Kalshi paper decisions",
        "",
        f"Observed {snap['at']}. Ten contracts per match.",
        "",
        "| Match | Fair win probability and stress range, first team | Whole-cent buy ceilings, first / second | Paper decision |",
        "|---|---:|---:|---|",
    ]
    for row in sorted(snap["rows"].values(), key=lambda r: (r["start"], r["teams"][0])):
        a, b = row["teams"]
        f = row["fair"][a]
        lim = row["limits_c"]
        opt = row.get("frozen_entry") if row["decision"] == "HOLD" else row["best"]
        action = f"{row['decision']} · {row['reason']}"
        if opt:
            cost = opt["execution"]
            action += f" · {opt['ticker']}, {display(opt['team'])} {opt['side'].upper()} at {cost['ask_c']:.2f}¢ × {cost['qty']}, fee ${cost['fee_usd']:.3f}, net EV {opt['net_c']:+.2f}¢/contract"
        elif row["options"]:
            depth = max(o["available"] for o in row["options"])
            action += f" · up to {depth:g} contracts displayed on one side"
        lines.append(
            f"| {display(a)} vs {display(b)} | {f['p']:.1%} ({f['low']:.1%}–{f['high']:.1%}) | {lim[a]}¢ / {lim[b]}¢ | {action} |"
        )
    lines += [
        "",
        (
            f"{stats['unique_matches']} unique matches logged. {stats['ever_taken']} paper entries. "
            f"{stats['settled_entries']} settled. Realized paper P&L ${stats['realized_net_usd']:.2f}."
        ),
        "",
        f"{stats['n_scored']} matches scored for calibration. {stats['clv_n']} entries have a liquid closing comparison.",
    ]
    if stats["finished_without_pregame"]:
        lines.append(
            f"{len(stats['finished_without_pregame'])} completed fixtures had no observed pre-match decision."
        )
    if stats["n_scored"]:
        lines.append(f"Brier {stats['brier']:.4f}. Log loss {stats['log_loss']:.4f}.")
    if stats["clv_n"]:
        lines.append(
            f"Mean closing midpoint advantage over all-in entry {stats['avg_clv_net_c']:+.2f}¢ per contract."
        )
    if snap.get("roster_changed"):
        lines += ["", "PGL’s roster publication changed. Review it before taking a paper position."]
    if snap["unmatched"]:
        lines += [
            "",
            "Unmatched Singapore contracts require fixture/terms review: "
            + ", ".join(snap["unmatched"]),
        ]
    return "\n".join(lines) + "\n"


def publish(path, text):
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf8") as f:
        f.write(text)
    Path(f.name).replace(path)


def main():
    with (
        sqlite3.connect(LEDGER, timeout=45) as db,
        httpx.Client(timeout=20, follow_redirects=True) as client,
    ):
        initialize(db)
        snap = scan(db, client)
        grade(db, client)
        stats = report(db, snap)
        text = sheet(snap, stats)
        publish(HERE / "latest.md", text)
        publish(HERE / "performance.json", json.dumps(stats, indent=2) + "\n")
        # Preserve the first publication separately for reproduction and post-event auditing.
        first = db.execute("SELECT payload FROM scans ORDER BY at LIMIT 1").fetchone()[0]
        frozen = HERE / "opening-snapshot.json.gz"
        if not frozen.exists():
            with frozen.open("xb") as f:
                f.write(first)
        print(text)
        print("Catalog counts:", {k: len(v) for k, v in snap["listed"].items()})


if __name__ == "__main__":
    main()
