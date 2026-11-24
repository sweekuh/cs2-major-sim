"""Poll PGL and turn changes into match_start, map_end and match_finish events.

Run from the project root:

    uv run --frozen python -m analysis.singapore_live.watch

Each event is appended to ``state/events.jsonl`` and passed to the hooks:

- ``--price-on``: run the live pricer (``analysis.singapore_live.price``) for these event types.
- ``--post URL``: POST lifecycle events as JSON. Failed deliveries stay queued for that URL.
  Receivers can deduplicate retries using the Idempotency-Key header.
- ``--wake-on``: exit after a poll that produced one of these event types, so the
  supervising agent (or a shell loop) can react and restart the watcher.

State is diffed against ``state/feed.json``, so changes that happen while the watcher is
stopped still produce events when it restarts. Exit codes: 0 woke on an event, 2 reached
``--max-minutes``, 3 the feed kept failing, 4 nothing is live and the next match is beyond
``--max-minutes`` (the output gives its start time).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from . import feed

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
ROOT = HERE.parents[1]
EVENT_TYPES = (
    "fixture_set", "fixture_changed", "maps_set", "match_start",
    "round_update", "map_end", "match_finish", "result_corrected",
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def map_named(name: str) -> bool:
    return bool(name) and name not in ("de_", "tba", "tbd")


def diff(prev: dict[str, feed.Fixture] | None, cur: dict[str, feed.Fixture], *, at: str,
         updated: dict | None = None) -> list[dict]:
    """Events implied by moving from ``prev`` to ``cur``. A first run (``prev`` None) is silent."""
    if prev is None:
        return []
    events = []
    for key, c in cur.items():
        p = prev.get(key)
        base = {
            "key": key, "stage": c.stage, "round": c.round, "bo": c.bo, "a": c.a, "b": c.b,
            "score": list(c.score), "status": c.status, "detected_at": at,
            "feed_updated_at": (updated or {}).get(c.stage) if updated else None,
        }
        if p is None or (not p.a and not p.b):
            if c.a and c.b:
                events.append({**base, "type": "fixture_set", "start": c.start})
            if p is None:
                continue
        elif (p.a, p.b) != (c.a, c.b):
            events.append({**base, "type": "fixture_changed", "was": [p.a, p.b]})
            continue
        if not c.a or not c.b:
            continue
        before = [m for m, _, _ in p.maps if map_named(m)]
        after = [m for m, _, _ in c.maps if map_named(m)]
        if after != before and len(after) > len(before):
            events.append({**base, "type": "maps_set", "maps": after})
        played = any(ra or rb for _, ra, rb in c.maps) or sum(c.score) > 0
        started_before = p.status != "upcoming" or any(ra or rb for _, ra, rb in p.maps) or sum(p.score) > 0
        if not started_before and (c.status != "upcoming" or played):
            events.append({**base, "type": "match_start", "start": c.start,
                           "late_by_s": round((datetime.fromisoformat(at) - datetime.fromisoformat(c.start)).total_seconds())})
        for i, (cm, pm) in enumerate(zip(c.maps, p.maps)):
            if cm[1:] != pm[1:] and (cm[1] or cm[2]):
                events.append({**base, "type": "round_update", "map_index": i + 1, "map": cm[0],
                               "rounds": [cm[1], cm[2]]})
        # One event per map that finished since the last poll, oldest first.
        done_before, done_now = sum(p.score), sum(c.score)
        for n in range(done_before + 1, done_now + 1):
            idx = n - 1
            name, ra, rb = c.maps[idx] if idx < len(c.maps) else ("", 0, 0)
            winner = c.a if ra > rb else c.b if rb > ra else None
            events.append({**base, "type": "map_end", "map_index": n, "map": name,
                           "rounds": [ra, rb], "map_winner": winner})
        if p.status != "end" and c.status == "end":
            events.append({**base, "type": "match_finish", "winner": c.winner})
        elif p.status == c.status == "end" and p.winner != c.winner:
            events.append({**base, "type": "result_corrected", "previous_winner": p.winner,
                           "previous_score": list(p.score), "winner": c.winner})
    order = {t: i for i, t in enumerate(EVENT_TYPES)}
    return sorted(events, key=lambda e: order[e["type"]])


def load_checkpoint() -> dict:
    path = STATE / "feed.json"
    if not path.exists():
        return {"pending_posts": {}}
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    checkpoint.setdefault("pending_posts", {})  # migrate pre-outbox checkpoints
    return checkpoint


def save_checkpoint(checkpoint: dict) -> None:
    STATE.mkdir(exist_ok=True)
    tmp = STATE / "feed.json.tmp"
    tmp.write_text(json.dumps(checkpoint, indent=1), encoding="utf-8")
    tmp.replace(STATE / "feed.json")


def append(name: str, rows: list[dict]) -> None:
    if rows:
        STATE.mkdir(exist_ok=True)
        with open(STATE / name, "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")


def live_and_next(fixtures: dict[str, feed.Fixture], at: datetime):
    live = [f for f in fixtures.values() if f.status == "live" or (
        f.status == "upcoming" and f.a and f.b and (any(r1 or r2 for _, r1, r2 in f.maps) or sum(f.score)))]
    upcoming = sorted(datetime.fromisoformat(f.start) for f in fixtures.values()
                      if f.status == "upcoming" and f.a and f.b)
    # A match past its scheduled start counts as imminent until PGL marks it live or finished.
    nxt = upcoming[0] if upcoming else None
    return live, nxt


def run_pricer(reason: str, timeout: int) -> dict:
    cmd = [sys.executable, "-m", "analysis.singapore_live.price", "--reason", reason, "--quiet"]
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"pricer timed out after {timeout}s"}
    if out.returncode != 0:
        return {"ok": False, "error": (out.stderr or out.stdout).strip()[-1500:]}
    try:
        return {"ok": True, **json.loads(out.stdout.strip().splitlines()[-1])}
    except (ValueError, IndexError):
        return {"ok": False, "error": "pricer printed no summary", "stdout": out.stdout[-800:]}


def deliver_pending(client, url: str, destination: str, checkpoint: dict) -> None:
    """Deliver in order. A crash after the receiver accepts a POST can replay its key."""
    pending = checkpoint["pending_posts"]
    queue = pending.get(destination, [])
    while queue:
        event = queue[0]
        event_id = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
        try:
            response = client.post(url, json=event, headers={"Idempotency-Key": event_id}, timeout=10)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # HTTPX exception messages may contain the secret webhook URL.
            error = (f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError)
                     else type(exc).__name__)
            append("errors.jsonl", [{"at": now().isoformat(), "where": "post", "error": error,
                                     "key": event["key"], "type": event["type"]}])
            return
        queue.pop(0)
        if not queue:
            del pending[destination]
        save_checkpoint(checkpoint)


def track_prices(client, live: list[feed.Fixture], at: str) -> None:
    """Record Polymarket mids for live matches each poll, to time feed events against prices."""
    try:
        from .markets import poly_match_tokens, poly_midpoints
        tokens = poly_match_tokens(client)
        wanted = {}
        for f in live:
            info = tokens.get(frozenset((f.a, f.b)))
            if info:
                wanted[f.key] = info
        mids = poly_midpoints(client, [i["tokens"][0] for i in wanted.values()])
        rows = []
        for key, info in wanted.items():
            f = next(x for x in live if x.key == key)
            mid = mids.get(info["tokens"][0])
            if mid is None:
                continue
            p_a = mid if info["outcomes"][0] == f.a else 1 - mid
            rows.append({"at": at, "key": key, "a": f.a, "b": f.b, "p_a": round(p_a, 4),
                         "score": list(f.score), "maps": [list(m) for m in f.maps]})
        append("ticks.jsonl", rows)
    except Exception as exc:  # price tracking never stops the watcher
        append("errors.jsonl", [{"at": at, "where": "track_prices", "error": repr(exc)[:500]}])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=15, help="seconds between polls while a match is live or imminent")
    ap.add_argument("--idle-interval", type=float, default=60, help="seconds between polls otherwise")
    ap.add_argument("--max-minutes", type=float, default=110)
    ap.add_argument("--wake-on", default="match_start,map_end,match_finish,fixture_changed,result_corrected")
    ap.add_argument("--price-on", default="match_start,map_end,match_finish,fixture_set,result_corrected")
    ap.add_argument("--post", help="outbound webhook URL that receives each event as JSON")
    ap.add_argument("--no-track-prices", action="store_true")
    ap.add_argument("--pricer-timeout", type=int, default=240)
    ap.add_argument("--price-every-live", type=float, default=180,
                    help="also rerun the pricer this often (seconds) while a match is live; 0 disables")
    ap.add_argument("--stages", default="1,2,3,4")
    ap.add_argument("--once", action="store_true", help="poll once, report, and exit")
    args = ap.parse_args(argv)
    wake = set(filter(None, args.wake_on.split(",")))
    price_on = set(filter(None, args.price_on.split(",")))
    stages = tuple(int(s) for s in args.stages.split(","))
    started, failures, last_error = now(), 0, None
    woke, pricing, last_priced = [], None, 0.0
    destination = hashlib.sha256(args.post.encode()).hexdigest() if args.post else None
    checkpoint = load_checkpoint()
    prev = ({k: feed.from_dict(v) for k, v in checkpoint["fixtures"].items()}
            if "fixtures" in checkpoint else None)
    with httpx.Client(timeout=20) as client:
        while True:
            at = now()
            try:
                cur, updated = feed.fetch(client, stages)
                failures = 0
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                failures += 1
                last_error = repr(exc)[:500]
                append("errors.jsonl", [{"at": at.isoformat(), "where": "feed", "error": last_error}])
                if args.post:
                    deliver_pending(client, args.post, destination, checkpoint)
                if failures >= 20:
                    print(json.dumps({"exit": "feed_failing", "error": last_error}))
                    return 3
                time.sleep(min(60, 5 * failures))
                continue
            events = diff(prev, cur, at=at.isoformat(), updated=updated)
            if args.post:
                outbound = [e for e in events if e["type"] != "round_update"]
                if outbound:
                    checkpoint["pending_posts"].setdefault(destination, []).extend(outbound)
            checkpoint.update(at=at.isoformat(), updated=updated,
                              fixtures={k: f.asdict() for k, f in cur.items()})
            save_checkpoint(checkpoint)
            prev = cur
            append("events.jsonl", events)
            if args.post:
                deliver_pending(client, args.post, destination, checkpoint)
            live, nxt = live_and_next(cur, at)
            if live and not args.no_track_prices:
                track_prices(client, live, at.isoformat())
            reasons = sorted({e["type"] for e in events} & price_on)
            if not reasons and live and args.price_every_live and time.time() - last_priced >= args.price_every_live:
                reasons = ["live_tick"]
            if reasons:
                last_priced = time.time()
                pricing = run_pricer(",".join(reasons), args.pricer_timeout)
                append("pricer_runs.jsonl", [{"at": at.isoformat(), "reason": reasons, **{k: v for k, v in pricing.items() if k != "stdout"}}])
            woke += [e for e in events if e["type"] in wake]
            elapsed = (now() - started).total_seconds() / 60
            summary = {
                "at": at.isoformat(), "feed_updated": updated,
                "live": [[f.key, f.a, f.b, list(f.score), [list(m) for m in f.maps if m[1] or m[2]]] for f in live],
                "next_start": nxt.isoformat() if nxt else None,
                "events": [{k: e[k] for k in ("type", "key", "a", "b", "score") if k in e}
                           | {k: e[k] for k in ("map_index", "map", "rounds", "map_winner", "winner",
                                                "previous_winner", "previous_score", "late_by_s") if k in e}
                           for e in woke],
                "pending_posts": len(checkpoint["pending_posts"].get(destination, [])),
                "pricing": pricing,
            }
            if args.once:
                print(json.dumps({"exit": "once", **summary}, indent=1))
                return 0
            if woke:
                print(json.dumps({"exit": "event", **summary}, indent=1))
                return 0
            if elapsed >= args.max_minutes:
                print(json.dumps({"exit": "max_minutes", **summary}, indent=1))
                return 2
            soon = nxt is not None and nxt - at < timedelta(minutes=20)
            if not summary["pending_posts"] and not live and not soon and nxt is not None and nxt - at > timedelta(minutes=args.max_minutes - elapsed):
                print(json.dumps({"exit": "idle", **summary}, indent=1))
                return 4
            time.sleep(args.interval if live or soon else args.idle_interval)


if __name__ == "__main__":
    sys.exit(main())
