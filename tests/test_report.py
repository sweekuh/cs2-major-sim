"""monitor.report — EV report assembly, ranking, markdown rendering, and disk write.

Pure stdlib (no numpy/network): feeds hand-made edge rows (the shape the script produces from
``monitor.edge.stake_row``) and pins the report dict + markdown + file output.
"""

from __future__ import annotations

import json

from monitor.report import build_report, to_markdown, write_report

_ROWS = [
    {"ticker": "KXMENWORLDCUP-26-BRA", "team": "Brazil", "type": "champion", "side": "yes",
     "model": 0.182, "mid": 0.150, "net_edge": 0.025, "kelly": 0.038, "stake": 9.5},
    {"ticker": "KXWCGROUPWIN-26A-MEX", "team": "Mexico", "type": "group_winner", "side": "no",
     "model": 0.300, "mid": 0.420, "net_edge": 0.090, "kelly": 0.120, "stake": 30.0},
]


def test_build_report_sorts_by_net_edge_and_stamps_meta():
    rep = build_report(_ROWS, meta={"source": "fixture:x", "n_markets": 5})
    assert [e["ticker"] for e in rep["edges"]] == [
        "KXWCGROUPWIN-26A-MEX",  # net 0.090 first
        "KXMENWORLDCUP-26-BRA",  # net 0.025
    ]
    assert rep["meta"]["n_edges"] == 2
    assert rep["meta"]["source"] == "fixture:x"
    assert "generated_at" in rep["meta"]


def test_build_report_empty():
    rep = build_report([], meta={"source": "live:keyless"})
    assert rep["edges"] == []
    assert rep["meta"]["n_edges"] == 0


def test_to_markdown_has_table_rows_and_honesty_note():
    md = to_markdown(build_report(_ROWS, meta={"source": "fixture:x"}))
    assert "# Kalshi World Cup — EV report" in md
    assert "| ticker | team | type | side |" in md
    assert "Brazil" in md and "Mexico" in md
    # net_edge formatted to 3dp, stake to 2dp.
    assert "0.090" in md and "30.00" in md
    assert "CLV vs the sharp close" in md


def test_to_markdown_empty_says_no_signals():
    md = to_markdown(build_report([], meta={"source": "live:keyless"}))
    assert "No +EV signals above threshold" in md


def test_write_report_writes_json_and_md(tmp_path):
    rep = build_report(_ROWS, meta={"source": "fixture:x"})
    jp = tmp_path / "ev_report.json"
    mp = tmp_path / "ev_report.md"
    write_report(rep, json_path=jp, md_path=mp)
    assert jp.exists() and mp.exists()
    loaded = json.loads(jp.read_text())
    assert loaded["meta"]["n_edges"] == 2
    assert loaded["edges"][0]["ticker"] == "KXWCGROUPWIN-26A-MEX"
    assert "EV report" in mp.read_text()


def test_write_report_json_only(tmp_path):
    jp = tmp_path / "sub" / "ev.json"  # parent dir is created
    write_report(build_report(_ROWS), json_path=jp)
    assert jp.exists()
