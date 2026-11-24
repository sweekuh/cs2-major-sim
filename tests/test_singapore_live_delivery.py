"""Watcher checkpoint, webhook recovery, and official result corrections."""

import json
from dataclasses import replace

import httpx

from analysis.singapore_live import feed, watch


AT = "2026-11-25T08:00:00+00:00"
URL = "https://receiver.invalid/private-token"
UPCOMING = feed.Fixture("s1-00", 1, "Opening round", 1, 1, AT, "upcoming",
                        "Imperial", "FlyQuest", (0, 0), (("de_nuke", 0, 0),))
FINISHED = replace(UPCOMING, status="end", score=(1, 0), maps=(("de_nuke", 13, 9),))


def seed_old_checkpoint(path, fixture):
    (path / "feed.json").write_text(json.dumps({
        "at": AT, "updated": {"1": AT}, "fixtures": {fixture.key: fixture.asdict()},
    }), encoding="utf-8")


def test_webhook_retries_unacknowledged_events_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "STATE", tmp_path)
    seed_old_checkpoint(tmp_path, UPCOMING)
    monkeypatch.setattr(feed, "fetch", lambda *_: ({FINISHED.key: FINISHED}, {1: AT}))
    statuses = iter([204, 503, 204, 200])
    attempts = []

    def receiver(client, url, *, json, headers, timeout):
        assert url == URL
        attempts.append((json["type"], headers["Idempotency-Key"]))
        return httpx.Response(next(statuses), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", receiver)
    args = ["--once", "--price-on", "", "--post"]
    assert watch.main([*args, URL]) == 0
    first = watch.load_checkpoint()
    assert first["fixtures"][FINISHED.key]["status"] == "end"
    queued, = first["pending_posts"].values()
    assert [e["type"] for e in queued] == ["map_end", "match_finish"]
    assert [event for event, _ in attempts] == ["match_start", "map_end"]

    # The same fixture after restart has no new transitions. Another destination
    # must never receive the first receiver's backlog.
    assert watch.main([*args, "https://different.invalid/hook"]) == 0
    assert watch.main([*args, URL]) == 0
    assert [event for event, _ in attempts] == ["match_start", "map_end", "map_end", "match_finish"]
    assert attempts[1] == attempts[2]
    assert watch.load_checkpoint()["pending_posts"] == {}
    assert watch.main([*args, URL]) == 0
    assert len(attempts) == 4
    assert json.loads((tmp_path / "errors.jsonl").read_text())["error"] == "HTTP 503"
    assert all("private-token" not in path.read_text() for path in tmp_path.iterdir())


def test_changed_official_winner_posts_reprices_and_wakes_once(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(watch, "STATE", tmp_path)
    seed_old_checkpoint(tmp_path, FINISHED)
    correction = replace(FINISHED, score=(0, 1), maps=(("de_nuke", 9, 13),))
    monkeypatch.setattr(feed, "fetch", lambda *_: ({correction.key: correction}, {1: AT}))
    posts, reasons = [], []

    def receiver(client, url, *, json, headers, timeout):
        posts.append(json)
        return httpx.Response(204, request=httpx.Request("POST", url))

    def reprice(reason, timeout):
        reasons.append(reason)
        return {"ok": True}

    monkeypatch.setattr(httpx.Client, "post", receiver)
    monkeypatch.setattr(watch, "run_pricer", reprice)
    assert watch.main(["--post", URL, "--max-minutes", "0"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["exit"] == "event"
    event, = summary["events"]
    assert event["type"] == "result_corrected"
    assert (event["previous_winner"], event["previous_score"]) == ("Imperial", [1, 0])
    assert (event["winner"], event["score"]) == ("FlyQuest", [0, 1])
    assert watch.main(["--post", URL, "--once"]) == 0
    assert reasons == ["result_corrected"]
    assert [e["type"] for e in posts] == ["result_corrected"]
