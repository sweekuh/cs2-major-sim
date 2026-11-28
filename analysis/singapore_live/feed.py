"""PGL's official Singapore results feed, normalized into fixtures.

The feed is polled; PGL offers no push notifications. ``x-updated-at`` on each response is
PGL's own last-change time, which lets the watcher measure how far the feed trails play.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from .names import canon

PGL = "https://news.pglesports.com/api/"
SGT = timezone(timedelta(hours=8))
HEADERS = {"User-Agent": "Mozilla/5.0 (cs2-major-sim live watcher)"}
STATUSES = {"upcoming", "live", "end"}


@dataclass(frozen=True)
class Fixture:
    key: str  # "s{stage}-{row}", the row's position in PGL's list for that stage
    stage: int  # 1-3 are Swiss stages, 4 is the playoff bracket
    label: str
    round: int | str
    bo: int
    start: str  # ISO 8601, UTC
    status: str
    a: str | None
    b: str | None
    score: tuple[int, int]
    maps: tuple[tuple[str, int, int], ...]  # (map, rounds for a, rounds for b)
    # bo3.gg's view of a live match: True while a map is being played, False between maps,
    # None when unknown. Neither feed reports live round scores, so this is the only signal.
    underway: bool | None = None

    @property
    def winner(self) -> str | None:
        if self.status != "end" or self.score[0] == self.score[1]:
            return None
        return self.a if self.score[0] > self.score[1] else self.b

    def asdict(self) -> dict:
        return asdict(self)


def round_of(stage: int, label: str) -> int | str:
    label = label.strip().lower()
    if stage == 4:
        return label
    if label.startswith("opening round"):
        return 1
    found = re.match(r"round (\d)", label)
    if not found:
        raise ValueError(f"Unrecognized PGL round label: {label!r}")
    return int(found[1])


def final_score(a: int, b: int) -> bool:
    """A score a CS2 map can end on: 13 to at most 11 in regulation, or an overtime win.

    Each overtime starts level (12-12, 15-15, ...) and goes to the first team to win four of six
    rounds, so it ends 16-12, 16-13 or 16-14, then 19-15 to 19-17, and so on. Scores PGL shows
    while entering one side at a time (10-0, 14-0, 19-0) are not on that list.
    """
    win, lose = max(a, b), min(a, b)
    if win == 13:
        return lose <= 11
    return win > 13 and (win - 13) % 3 == 0 and win - 4 <= lose <= win - 2


def map_named(name: str) -> bool:
    return bool(name) and name not in ("de_", "tba", "tbd")


def map_finished(name: str, a: int, b: int) -> bool:
    """PGL blanks a map's name while editing its row, so a finished map also needs its name."""
    return map_named(name) and final_score(a, b)


def parse(stage: int, rows: list[dict]) -> dict[str, Fixture]:
    fixtures = {}
    for i, m in enumerate(rows):
        if m["status"] not in STATUSES:
            raise ValueError(f"Unrecognized PGL status {m['status']!r}")
        if m.get("timeZone") != "SGT":
            raise ValueError(f"PGL time zone changed to {m.get('timeZone')!r}")
        local = datetime.strptime(f"{m['date']} {m['time']}", "%d.%m.%Y %H:%M")
        start = local.replace(tzinfo=SGT).astimezone(timezone.utc)
        bo = int(re.fullmatch(r"BO(\d)", m["format"])[1])
        maps = tuple(
            (mp.get("map") or "", int(mp.get("leftScore") or 0), int(mp.get("rightScore") or 0))
            for mp in m.get("maps") or []
        )
        score, status = (int(m.get("leftScore") or 0), int(m.get("rightScore") or 0)), m["status"]
        # PGL enters a map's rounds one side at a time and can count the map before both are in:
        # on November 26 Lynn Vision v PVISION read 1-1 with Dust2 at 10-0 for 8 seconds before
        # 0-2 with Dust2 at 10-13. On November 28 it showed Natus Vincere v PVISION ended 1-0
        # with an unnamed map at 13-0 (Ancient 13-10 a poll later) and Liquid v Eternal Fire at
        # 1-0 with an unnamed map at 19-0 (Anubis 19-17). A map with rounds that is not named
        # and on a final score is still being entered, so the series counts only finished maps
        # until PGL agrees.
        if any((ra or rb) and not map_finished(mp, ra, rb) for mp, ra, rb in maps):
            done = [(ra, rb) for mp, ra, rb in maps if map_finished(mp, ra, rb)]
            counted = (sum(ra > rb for ra, rb in done), sum(rb > ra for ra, rb in done))
            if counted != score:
                score, status = counted, "live" if status == "end" else status
        fixtures[f"s{stage}-{i:02d}"] = Fixture(
            key=f"s{stage}-{i:02d}",
            stage=stage,
            label=m["round"].strip(),
            round=round_of(stage, m["round"]),
            bo=bo,
            start=start.isoformat(),
            status=status,
            a=canon(m.get("leftTeam"), strict=False),
            b=canon(m.get("rightTeam"), strict=False),
            score=score,
            maps=maps,
        )
    return fixtures


def fetch(client, stages=(1, 2, 3, 4)) -> tuple[dict[str, Fixture], dict]:
    """Return all fixtures for the requested stages plus PGL's update times per stage."""
    fixtures, updated = {}, {}
    for stage in stages:
        url = PGL + ("playoffsEndpoint" if stage == 4 else "groupStageEndpoint")
        params = {} if stage == 4 else {"stage": stage}
        r = client.get(url, params=params, headers=HEADERS)
        r.raise_for_status()
        updated[stage] = r.headers.get("x-updated-at")
        fixtures.update(parse(stage, r.json()))
    return fixtures, updated


def from_dict(d: dict) -> Fixture:
    return Fixture(**{**d, "score": tuple(d["score"]), "maps": tuple(tuple(m) for m in d["maps"])})


# ---------------------------------------------------------------- live overlay (bo3.gg)
# PGL publishes results in batches (on Nov 25 its feed still showed round 3 as upcoming
# twenty minutes after both openers began). bo3.gg's public match feed marks a match
# current at kickoff and records each finished map's winner and round score, so it is
# layered over PGL for live state. PGL stays authoritative: once PGL marks a match ended,
# its result wins, and a different bo3.gg result surfaces as ``result_corrected``.
BO3 = "https://api.bo3.gg/api/v1/matches"
BO3_TOURNAMENTS = {1: 6269, 2: 6268, 3: 4226, 4: 4226}
LIVE_OVERLAY = True  # tests switch this off so they stay offline


def _utc(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def overlay(fixtures: dict[str, Fixture], bo3_by_stage: dict[int, list[dict]]) -> dict[str, Fixture]:
    """Return fixtures with bo3.gg live state applied where PGL has not finished the match."""
    from dataclasses import replace

    out = dict(fixtures)
    for f in fixtures.values():
        if f.status == "end" or not f.a or not f.b:
            continue
        found = []
        for m in bo3_by_stage.get(f.stage, []):
            t1 = canon((m.get("team1") or {}).get("name"), strict=False)
            t2 = canon((m.get("team2") or {}).get("name"), strict=False)
            if {t1, t2} == {f.a, f.b} and m.get("start_date") and \
                    abs((_utc(m["start_date"]) - _utc(f.start)).total_seconds()) <= 12 * 3600:
                found.append((m, t1, t2))
        if len(found) != 1:
            continue
        m, t1, t2 = found[0]
        if m.get("status") not in ("current", "finished") or int(m.get("bo_type") or 0) != f.bo:
            continue
        games = sorted(m.get("games") or [], key=lambda g: g.get("number") or 0)
        if m["status"] == "current" and not any(g.get("status") in ("current", "finished") for g in games):
            continue  # bo3.gg marks a match current around the veto and can flip back; wait for a map
        # Map winners carry the in-game clan tag ("FLY", "GAMDOM IMPERIAL"), so match on team id first.
        ids = {t["id"]: team for t, team in ((m.get("team1") or {}, t1), (m.get("team2") or {}, t2))
               if t.get("id") is not None}
        maps = []
        for i, g in enumerate(games):
            name = g.get("map_name") or (f.maps[i][0] if i < len(f.maps) else "")  # keep PGL's veto
            if g.get("status") == "finished" and g.get("winner_clan_score") is not None:
                winner = ids.get((g.get("winner_team_clan") or {}).get("team_id")) or \
                    canon(g.get("winner_clan_name"), strict=False)
                ws, ls = int(g["winner_clan_score"]), int(g["loser_clan_score"])
                if winner == f.a:
                    maps.append((name, ws, ls))
                elif winner == f.b:
                    maps.append((name, ls, ws))
                else:
                    break  # an unrecognized map winner ends what we trust from this record
            else:
                maps.append((name, 0, 0))
        maps = tuple(maps[: f.bo]) + tuple((f.maps[i][0] if i < len(f.maps) else "", 0, 0)
                                           for i in range(len(maps), f.bo))
        won = (sum(a > b for _, a, b in maps), sum(b > a for _, a, b in maps))
        if m["status"] == "finished":
            s1, s2 = int(m.get("team1_score") or 0), int(m.get("team2_score") or 0)
            score = (s1, s2) if t1 == f.a else (s2, s1)
            if max(score) != f.bo // 2 + 1 or score[0] == score[1]:
                continue  # not a decisive series in this format; wait for PGL
            out[f.key] = replace(f, status="end", score=score, maps=maps)
        else:
            if max(won) >= f.bo // 2 + 1:
                continue  # maps say it is over but the match is not marked finished
            underway = any(g.get("status") == "current" for g in games)
            if sum(f.score) >= sum(won) and (sum(f.score) or any(ra or rb for _, ra, rb in f.maps)):
                # PGL is at least as far along (bo3.gg can list a map finished before naming its
                # winner): keep PGL's score and round scores and only mark the match live.
                out[f.key] = replace(f, status="live", underway=underway)
                continue
            out[f.key] = replace(f, status="live", score=won, maps=maps, underway=underway)
    return out


def fetch_bo3(client, stages) -> dict[int, list[dict]]:
    out = {}
    for stage in stages:
        r = client.get(BO3, params={"filter[matches.tournament_id][eq]": BO3_TOURNAMENTS[stage],
                                    "with": "games,teams", "page[limit]": 100}, headers=HEADERS)
        r.raise_for_status()
        out[stage] = r.json().get("results", [])
    return out


def with_live(client, fixtures: dict[str, Fixture]) -> tuple[dict[str, Fixture], str | None]:
    """PGL fixtures with bo3.gg live state layered on. Returns (fixtures, error or None)."""
    if not LIVE_OVERLAY:
        return fixtures, None
    stages = sorted({f.stage for f in fixtures.values() if f.status != "end" and f.a and f.b})
    if not stages:
        return fixtures, None
    try:
        return overlay(fixtures, fetch_bo3(client, stages)), None
    except Exception as exc:  # the overlay is an accelerator; PGL alone remains usable
        return fixtures, f"bo3.gg overlay failed: {type(exc).__name__}"
