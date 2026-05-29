---
status: partial
phase: 02-streamlit-ui-shell
source: [02-VERIFICATION.md]
started: 2026-05-29
updated: 2026-05-29
---

## Current Test

[manual visual verification — orchestrator running app via /browse]

## Tests

### 1. CI mini-bars render under every probability number
expected: every P(3-0)/P(advance)/P(0-3) cell shows the number + a thin always-visible bar
result: [pending]

### 2. Colorblind-safe blue/amber status palette (never red/green), glyph+label
expected: advanced=blue, eliminated=amber, ASCII glyph + text label
result: [pending]

### 3. Progress bar live-updates over ~15s (not a blank freeze)
expected: st.progress + running P(advance) tally during the run
result: [pending]

### 4. Cross-OS launch (Mac/Linux)
expected: `uv run streamlit run app.py` launches on Mac/Linux
result: [pending — author on Windows; needs a friend to confirm]

### 5. README quickstart prose / DX-04 ordering reads naturally
expected: clone → run → first-sim-no-key → numbers meaning → seed reconcile → cold-start drill
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
