"""Persisted EV report: ranked edge rows + run metadata -> a JSON artifact + a markdown table.

The monitor (``scripts.monitor_wc`` / ``scripts.ev_report``) prints to the console; this turns the
same ranked signals into a SAVED, diffable record so a run is reviewable later and the CLV oracle
(``monitor.signal_log``) has a companion human-readable snapshot.

Pure stdlib by design — NO numpy / httpx / cryptography / engine import — so the report layer is
unit-testable in isolation and stays off the heavy import path. The caller flattens
``monitor.edge.EdgeSignal``s (via ``monitor.edge.stake_row``, optionally enriched with the team and
market title) into plain dict rows and hands them here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# Column order for the markdown table (key -> header). Rows missing a key render blank.
_COLUMNS = (
    ("ticker", "ticker"),
    ("team", "team"),
    ("type", "type"),
    ("side", "side"),
    ("model", "model"),
    ("mid", "mid"),
    ("net_edge", "net_edge"),
    ("kelly", "kelly"),
    ("stake", "stake $"),
)


def build_report(rows: list[dict], *, meta: dict | None = None) -> dict:
    """Assemble the report dict: ``{"meta": {...}, "edges": [...]}``, edges sorted best-first.

    ``rows`` are flattened edge dicts (``ticker``/``type``/``side``/``model``/``mid``/``net_edge``/
    ``kelly``/``stake`` and optionally ``team``/``title``). ``meta`` carries the run context
    (source, auth status, sim params, counts); a UTC ``generated_at`` and ``n_edges`` are stamped
    on automatically. Sorting by ``net_edge`` descending mirrors the console ranking.
    """
    edges = sorted(rows, key=lambda r: r.get("net_edge", 0.0), reverse=True)
    out_meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if meta:
        out_meta.update(meta)
    out_meta["n_edges"] = len(edges)
    return {"meta": out_meta, "edges": edges}


def _fmt(key: str, value) -> str:
    if value is None:
        return ""
    if key in ("model", "mid", "net_edge", "kelly") and isinstance(value, (int, float)):
        return f"{value:.3f}"
    if key == "stake" and isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value)


def to_markdown(report: dict) -> str:
    """Render the report as a markdown doc: a metadata header + the ranked edge table.

    Honest framing baked in (WORLDCUP §1/§2): this is a read-only, paper-only signal list; positive
    ``net_edge`` is already net of the exact Kalshi fee + half-spread, but CLV-vs-close is the only
    proof an edge is real.
    """
    meta = report.get("meta", {})
    edges = report.get("edges", [])
    lines: list[str] = ["# Kalshi World Cup — EV report", ""]
    # Metadata block.
    order = ["generated_at", "source", "authenticated", "n_markets", "n_edges", "n_unmapped",
             "threshold", "bankroll", "kelly_fraction", "n_sims", "seed"]
    seen = set()
    for k in order:
        if k in meta:
            lines.append(f"- **{k}**: {meta[k]}")
            seen.add(k)
    for k, v in meta.items():
        if k not in seen:
            lines.append(f"- **{k}**: {v}")
    lines.append("")
    if not edges:
        lines.append("_No +EV signals above threshold._")
        lines.append("")
    else:
        headers = [h for _, h in _COLUMNS]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for r in edges:
            lines.append("| " + " | ".join(_fmt(k, r.get(k)) for k, _ in _COLUMNS) + " |")
        lines.append("")
    lines.append("> Read-only, paper-only. `net_edge` is net of the exact Kalshi fee + half-spread; "
                 "CLV vs the sharp close is the only proof an edge is real (see docs/WORLDCUP.md).")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict, *, json_path: str | Path, md_path: str | Path | None = None) -> None:
    """Write the report JSON (always) and, if ``md_path`` is given, the markdown rendering."""
    jp = Path(json_path)
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    if md_path is not None:
        mp = Path(md_path)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(to_markdown(report), encoding="utf-8")
