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
