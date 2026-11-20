"""Render the same self-contained Stage 1 card in Streamlit and the static forecast."""

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from string import Template


def render(forecast, fixture):
    template = Template(Path(__file__).with_name("singapore_report.html").read_text(encoding="utf-8"))
    card = "".join(
        f'<section><h3>{escape(bucket)}</h3><p>{", ".join(map(escape, picks))}</p></section>'
        for bucket, picks in forecast["card"].items()
    )
    team_rows = []
    for row in sorted(forecast["teams"], key=lambda r: -r["qualify"]):
        metrics = "".join(f"<td>{row[k]:.1%}</td>" for k in ("sweep", "advance_pick", "winless", "qualify"))
        team_rows.append(f'<tr><th scope="row">{escape(row["team"])}</th>{metrics}</tr>')
    openers = []
    for q in forecast.get("updated_openers", fixture["openers"]):
        a, b = map(escape, q["teams"])
        url = "https://polymarket.com/event/" + escape(q["slug"], quote=True)
        openers.append(f'<li><a href="{url}">{a} vs {b}</a> · {(q["bid"] + q["ask"])/2:.1%} {a}</li>')
    sensitivity = forecast["sensitivity"]
    assess = forecast["evaluation"]
    swap = forecast["closest_swap"]
    model = forecast["model"]
    model_detail = {
        "Opener only": "Later matches use the November 19 Valve ratings.",
        "Half carry": "Later matches retain half the opening price adjustment in log-odds.",
        "Full carry": "Each opening pair retains its average Valve rating. Its full market-implied strength difference carries into later matches.",
        "Recent maps": "Later matches use opponent-adjusted map results from the preceding 60 days.",
    }[model]
    line = forecast["line_tests"][0]
    scenario = (f'At a hypothetical {line["tested"]:.1%} for {escape(line["team"])} to beat '
                f'{escape(line["opponent"])} (observed {line["current"]:.1%}),')
    edge = -100 * line["card_minus_alternative"]
    timestamp = datetime.fromisoformat(forecast["quotes_observed_at"]).astimezone(timezone.utc)
    return template.substitute(
        card=card, team_rows="".join(team_rows), openers="".join(openers),
        chance=f'{assess["p_ge5"]:.1%}', expected=f'{assess["expected_correct"]:.2f}',
        select_n=f'{forecast["n_select"]:,}', eval_n=f'{assess["n"]:,}',
        lo=f'{assess["ci95_sampling"][0]:.1%}', hi=f'{assess["ci95_sampling"][1]:.1%}',
        line_test=f'{scenario} the swap changes the pass rate by {edge:+.2f} percentage points with the other seven prices fixed.',
        model_detail=model_detail, bucket=escape(swap["bucket"]), delta=f'{100 * swap["card_minus_alternative"]:+.2f}',
        delta_lo=f'{100 * swap["ci95_delta"][0]:+.2f}', delta_hi=f'{100 * swap["ci95_delta"][1]:+.2f}',
        reserve=escape(swap["in"]), replaced=escape(swap["out"]), alternate=f'{swap["p_ge5"]:.1%}',
        scenarios="".join(f'<li>{escape(label)} · {s["p_ge5"]:.1%} over {s["n"]:,} runs</li>'
                          for label, s in sensitivity.items()),
        as_of=timestamp.strftime("%d %b %Y, %H:%M UTC"),
        **{key: escape(url, quote=True) for key, url in fixture["sources"].items()},
    )


def static_page(report):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Singapore 2026 · Stage 1 Pick’Em</title>
<style>body{{margin:0;background:#10151a;color:#edf3f6}}main{{max-width:980px;margin:auto}}
footer{{padding:18px 24px 48px;font:15px system-ui}}footer a{{color:#9cd9d1}}</style>
</head><body><main>{report}<footer><a href="cologne-2026.html">Cologne 2026 forecast archive</a></footer>
</main></body></html>
"""
