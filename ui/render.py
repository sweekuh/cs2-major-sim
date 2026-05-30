"""Inline HTML render helpers — Phase 2 CI mini-bars + number formatting (UI-04 / UI-06).

Imports NO streamlit — these are pure string builders, unit-tested without AppTest. The
app passes the returned strings to ``st.markdown(..., unsafe_allow_html=True)``.

XSS invariant (T-02-XSS, CLAUDE.md Security Domain): every argument to ci_bar_html is a
NUMERIC float. A team name or ANY user free-text is NEVER interpolated into the HTML — the
only string arg is ``hue``, which is validated against a strict ``#rrggbb`` pattern so a
``<script>`` payload cannot reach the markup. The full visual token polish (monospace
table, right-alignment) lands in plan 02; this is the bar substance (UI-04 partial).
"""

from __future__ import annotations

import html
import re

# Track colour behind the filled CI portion (UI-SPEC Color §contrast). The fill uses the
# status hue at full opacity; the remainder is this neutral track.
_TRACK = "#3A3D46"
_DEFAULT_HUE = "#3B82F6"  # status: advanced blue (never red/green — UI-06)
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

# --- UI-06 status tokens -----------------------------------------------------------------
# Colorblind-safe palette, LOCKED: advanced/live = blue #3B82F6, eliminated = amber #F59E0B.
# NEVER red/green (~8% of men fail colour alone, so the glyph + label is the REAL signal and
# colour is only reinforcement). Glyphs are ASCII (`/`, `o`, `x`) — NEVER `●`/`✓` (the Phase 1
# Windows cp1252 console lesson, CLAUDE.md). Shape mirrors RESEARCH "Status glyph + label".
_BLUE = "#3B82F6"
_AMBER = "#F59E0B"
_ACCENT = "#7C5CFC"  # the one reserved accent (CTA / hero number / active mode segment)

STATUS: dict[str, tuple[str, str, str]] = {
    "advanced": ("/", "secured", _BLUE),   # advanced / secured a slot
    "live": ("o", "live", _BLUE),          # still alive, advancing
    "eliminated": ("x", "dead", _AMBER),   # eliminated — amber, NEVER red
}


def fmt_pct(p: float, decimals: int = 1) -> str:
    """Format a probability 0..1 as a monospace-friendly percentage string (UI-06).

    Raises TypeError on a non-numeric argument — numbers only ever reach this (no free-text).
    """
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        raise TypeError(f"fmt_pct expects a numeric probability, got {type(p).__name__}")
    return f"{p * 100:.{decimals}f}%"


def ci_bar_html(p: float, lo: float, hi: float, hue: str = _DEFAULT_HUE) -> str:
    """Return inline HTML: a monospace percentage over a 4px Wilson CI bar (UI-04).

    ``p`` is the point probability (0..1); ``lo``/``hi`` are the Wilson band bounds (0..1)
    from the engine's ``Result.band_*``. ``hue`` is the fill colour and MUST match
    ``#rrggbb`` — any other string raises ValueError (XSS guard T-02-XSS). All of p/lo/hi
    must be numeric floats; a non-numeric value raises TypeError so a free-text payload can
    never be embedded into the unsafe_allow_html markup.
    """
    for name, val in (("p", p), ("lo", lo), ("hi", hi)):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise TypeError(
                f"ci_bar_html expects numeric {name}, got {type(val).__name__} "
                "(team names / free text must NEVER reach this HTML — T-02-XSS)"
            )
    if not isinstance(hue, str) or not _HEX_COLOR.match(hue):
        raise ValueError(
            f"ci_bar_html hue must be a #rrggbb hex colour, got {hue!r} (XSS guard)"
        )

    pct = fmt_pct(p)
    left = max(0.0, min(1.0, lo)) * 100
    width = max(0.0, min(1.0, hi) - max(0.0, lo)) * 100
    return (
        f'<div style="font-family:ui-monospace,monospace;text-align:right">{pct}</div>'
        f'<div style="height:4px;background:{_TRACK};border-radius:2px;position:relative">'
        f'<div style="position:absolute;left:{left:.1f}%;width:{width:.1f}%;'
        f'height:4px;background:{hue};border-radius:2px"></div>'
        f"</div>"
    )


def delta_tag_html(post: float, pre: float, *, eps: float = 0.0005) -> str:
    """Return a small signed percentage-POINT delta tag: ``post`` vs ``pre`` (both 0..1).

    For the LIVE "Delta probabilities" table (RESIM-02 — show the CHANGE, not a new static
    number). Colorblind-safe (UI-06): the ``+``/``-`` SIGN is the real signal; hue is only
    reinforcement — increase = blue, decrease = amber, no-change = muted grey. ASCII only
    (no Unicode arrows — the cp1252 lesson, CLAUDE.md). Both args MUST be numeric floats; a
    non-numeric value raises TypeError so no free-text reaches the unsafe_allow_html markup
    (T-02-XSS). ``eps`` (in 0..1 units) is the dead-band below which the change reads as flat.
    """
    for name, val in (("post", post), ("pre", pre)):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise TypeError(
                f"delta_tag_html expects numeric {name}, got {type(val).__name__} "
                "(team names / free text must NEVER reach this HTML — T-02-XSS)"
            )
    dpp = (post - pre) * 100.0  # percentage points
    if abs(post - pre) < eps:
        return (
            '<span style="color:#8A8F98;font-family:ui-monospace,monospace;font-size:11px">'
            "+0.0pp</span>"
        )
    hue = _BLUE if dpp > 0 else _AMBER
    sign = "+" if dpp > 0 else "-"
    return (
        f'<span style="color:{hue};font-family:ui-monospace,monospace;font-size:11px">'
        f"{sign}{abs(dpp):.1f}pp</span>"
    )


def status_badge_html(state: str) -> str:
    """Return a colorblind-safe status badge: ASCII glyph + text label + hue (UI-06).

    ``state`` MUST be one of the fixed STATUS keys (advanced/live/eliminated) — an unknown
    value raises KeyError so NO free-text reaches the unsafe_allow_html markup (T-02-XSS).
    Colour is ALWAYS paired with the glyph + label (the real signal); the hue is only
    reinforcement. Glyphs are ASCII (`/`/`o`/`x`), never Unicode (cp1252 console lesson).
    """
    if not isinstance(state, str) or state not in STATUS:
        raise KeyError(
            f"status_badge_html state must be one of {sorted(STATUS)}, got {state!r} "
            "(no free text — T-02-XSS)"
        )
    glyph, label, hue = STATUS[state]
    return (
        f'<span style="color:{hue};font-family:ui-monospace,monospace">'
        f"{glyph} {label}</span>"
    )


def hero_number_html(pct: float) -> str:
    """Return the one display-size hero number: 28px monospace in the reserved accent (UI-06).

    ``pct`` is a probability 0..1 (e.g. the P(>=5) ballot headline). Accent ``#7C5CFC`` is
    reserved for the CTA, the hero number, and the active mode segment ONLY — never status,
    CI bars, or ordinary text (UI-SPEC Color). Numeric input only; a non-numeric value raises
    TypeError so a free-text payload can never be embedded (T-02-XSS).
    """
    formatted = fmt_pct(pct)  # raises TypeError on non-numeric (XSS guard)
    return (
        f'<span style="font-size:28px;font-weight:600;'
        f'font-family:ui-monospace,monospace;color:{_ACCENT}">{formatted}</span>'
    )


# --- Phase 3: Pick'Em ballot panel (OPT-03 / OPT-05) -------------------------------------
# Team names ARE interpolated here (the ballot lists them), so unlike ci_bar_html they are
# HTML-escaped (html.escape) before reaching the unsafe_allow_html markup (T-03-XSS). Names
# come from the read-only fixture, not the rating editor, but escaping is defense-in-depth.

DIFF_MARK = "*"  # ASCII marker on a pick that differs between Ballot A and Ballot B (UI-06:
#                  never rely on colour alone — the glyph is the real signal, like STATUS).

_BALLOT_BUCKETS = (("3-0", "picks_30"), ("Advance", "picks_adv"), ("0-3", "picks_03"))


def _ballot_card_html(title: str, ballot, name_of: dict[int, str], diff: set[int]) -> str:
    """One ballot column: its 3-0 / Advance / 0-3 picks by team name; differing picks bolded
    with the ASCII DIFF_MARK so the A-vs-B difference reads without colour (OPT-03)."""
    sections = []
    for label, field_name in _BALLOT_BUCKETS:
        items = []
        for tid in getattr(ballot, field_name):
            name = html.escape(str(name_of.get(tid, tid)))
            if tid in diff:
                items.append(f"<li><strong>{name} {DIFF_MARK}</strong></li>")
            else:
                items.append(f"<li>{name}</li>")
        sections.append(
            f'<div style="font-family:ui-monospace,monospace;opacity:0.65;'
            f'font-size:12px">{label}</div>'
            f'<ul style="margin:0 0 8px 18px;padding:0">{"".join(items)}</ul>'
        )
    # ``title`` is a fixed in-code literal (never user input), so it is not escaped — escaping
    # would turn "P(>=5)" into "P(&gt;=5)" in the source string. Team NAMES are escaped above.
    return (
        f'<div style="flex:1">'
        f'<div style="font-weight:600;margin-bottom:4px">{title}</div>'
        f'{"".join(sections)}</div>'
    )


def ballot_columns(
    name_of: dict[int, str], ballot_a, ballot_b, diff_ids
) -> str:
    """Render Ballot A and Ballot B side by side, differing picks highlighted (OPT-03).

    ``name_of`` maps team id -> name; ``diff_ids`` is the set/sequence of team ids whose
    bucket assignment differs between the two ballots. All names are HTML-escaped.
    """
    diff = set(diff_ids)
    return (
        '<div style="display:flex;gap:24px">'
        f'{_ballot_card_html("A — E[correct] greedy", ballot_a, name_of, diff)}'
        f'{_ballot_card_html("B — Max P(>=5)", ballot_b, name_of, diff)}'
        "</div>"
    )


# --- Phase 4: record-bucket bracket (D6 / RESIM-04) --------------------------------------
# Swiss teams reconverge BY RECORD, so the bracket is record-bucket COLUMNS, never a tree
# (HANDOFF §10.5). Canonical column order: 0-0 -> 1-0/0-1 -> 2-0/1-1/0-2 -> 2-1/1-2 ->
# 3-0 (advanced) / 0-3 (eliminated). Each column is a vertical stack of team chips placed by
# current (wins, losses); a chip from a LOCKED result is solid (opacity 1), a simulated-only
# chip is faint (opacity ~0.5). Team names are html.escape-d (T-04-XSS, like _ballot_card_html).

# (wins, losses) -> human column label, in canonical left->right order.
_BRACKET_BUCKETS: tuple[tuple[tuple[int, int], str], ...] = (
    ((0, 0), "0-0"),
    ((1, 0), "1-0"),
    ((0, 1), "0-1"),
    ((2, 0), "2-0"),
    ((1, 1), "1-1"),
    ((0, 2), "0-2"),
    ((2, 1), "2-1"),
    ((1, 2), "1-2"),
    ((3, 0), "3-0 adv"),
    ((0, 3), "0-3 elim"),
)


def bracket_columns_html(bracket_view, name_of: dict[int, str]) -> str:
    """Render a BracketView as record-bucket COLUMNS — never a tree (D6 / RESIM-04).

    One ``<div>`` column per canonical (wins, losses) bucket, laid out in a ``display:flex``
    row; each column is a vertical stack of team chips placed by their record from
    ``bracket_view.records`` (``{id: (wins, losses)}``). A team that appears in any LOCKED
    edge (``bracket_view.locked_edges``) renders solid (``opacity:1``); a simulated-only team
    renders faint (``opacity:0.5``). Team names are HTML-escaped via ``name_of`` (XSS
    defense-in-depth, like ``_ballot_card_html``). No streamlit, no tree/connector markup.
    """
    # Team ids that are "locked" (appear in at least one locked pair) -> solid chip.
    locked_team_ids: set[int] = set()
    for edge in getattr(bracket_view, "locked_edges", set()):
        locked_team_ids |= set(edge)

    # Group team ids by their current record.
    by_record: dict[tuple[int, int], list[int]] = {}
    for tid, rec in bracket_view.records.items():
        by_record.setdefault(tuple(rec), []).append(tid)

    columns: list[str] = []
    for record, label in _BRACKET_BUCKETS:
        chips: list[str] = []
        for tid in sorted(by_record.get(record, []), key=lambda t: name_of.get(t, str(t))):
            name = html.escape(str(name_of.get(tid, tid)))
            opacity = "1" if tid in locked_team_ids else "0.5"
            chips.append(
                f'<div style="opacity:{opacity};font-family:ui-monospace,monospace;'
                f'font-size:12px;padding:2px 0">{name}</div>'
            )
        body = "".join(chips) if chips else (
            '<div style="opacity:0.3;font-size:11px">—</div>'
        )
        columns.append(
            f'<div data-bucket="{label}" style="flex:1;min-width:90px">'
            f'<div style="font-weight:600;font-size:11px;opacity:0.65;'
            f'margin-bottom:4px">{label}</div>{body}</div>'
        )
    return f'<div style="display:flex;gap:12px;overflow-x:auto">{"".join(columns)}</div>'


def correlated_pick_warning_text(name_a: str, name_b: str) -> str:
    """Plain-text copy for the correlated-0-3-in-R1 warning (OPT-05), rendered via st.warning
    (natively amber — colorblind-safe, never red/green; the leading ``!`` is the ASCII glyph).

    Names only (no markup); the two teams meet in Round 1 so they can't both go 0-3.
    """
    return (
        f"! Correlated 0-3 picks: {name_a} and {name_b} meet in Round 1 — "
        f"they can't both go 0-3, so Ballot A caps at 1 here. Ballot B avoids this."
    )
