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
        fixtures[f"s{stage}-{i:02d}"] = Fixture(
            key=f"s{stage}-{i:02d}",
            stage=stage,
            label=m["round"].strip(),
            round=round_of(stage, m["round"]),
            bo=bo,
            start=start.isoformat(),
            status=m["status"],
            a=canon(m.get("leftTeam"), strict=False),
            b=canon(m.get("rightTeam"), strict=False),
            score=(int(m.get("leftScore") or 0), int(m.get("rightScore") or 0)),
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
