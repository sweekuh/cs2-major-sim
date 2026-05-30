# Milestones: swiss-mc — Cologne 2026 Swiss MC & Pick'Em Optimizer

A running log of shipped milestones. Newest first. Full archives live in `.planning/milestones/`.

---

## v1.0 — Cologne 2026 Swiss-Stage Pick'Em (calibrated)

**Shipped:** 2026-05-30
**Phases:** 1-5 (14 plans)
**Archives:** [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md) · [v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md)

The calibrated Cologne Swiss-stage Pick'Em tool: engine + backtest, two-mode UI, dual-ballot
optimizer, conditional live re-sim, and a fail-soft three-provider odds ensemble.

**Key accomplishments:**

1. **Headless Valve Swiss engine + GATE-01 backtest** — reproduces Budapest 2025 Stage 1 pairings EXACTLY (R1-R5, incl. the 6-team priority-table rounds): Buchholz `Σ(opp.wins − opp.losses)`, difficulty-ranked fold, verbatim 15-row priority table. Seeds from the authoritative Valve VRS snapshot.
2. **Generator-first Monte Carlo** — reproducible chunked seeds (`SeedSequence.spawn` over pinned chunks), Wilson bands, full per-sim record sample retained, structural invariants Σ=2/8/2, closed-form Bo3 `p²(3−2p)` as a single Bernoulli draw.
3. **Two-mode Streamlit UI** — Pre-stage/Live toggle, always-visible inline CI bars on every cell, colorblind-safe blue/amber status with glyph+label, [INFERRED]-seed banner + reconcile, caveated trust badge, zero-config first run (no API key).
4. **Pick'Em optimizer** — dual ballots (greedy per-bucket baseline + P(≥5) hill-climb with re-bucketing), correlated-pick warning, scored against the stored sample (never a fresh MC run).
5. **Conditional re-sim + live mode** — round-by-round result locking, live/dead/secured status with a P(≥5)-from-here delta, record-bucket bracket (solid locked / faint simulated), illegal-lock rejection with reasons.
6. **Fail-soft three-provider odds ensemble** — de-vig + log-opinion pool, ratings back-solve (series→map inversion + numpy-only logistic fit), epistemic Beta outer loop; never gates, needs no API key, writes a read-only cache the app only reads.

**Stats:** 113 tests passing · GATE-01 Budapest 2025 backtest GREEN · ~7,000 LOC Python · 80 commits (2026-05-28 → 2026-05-30) · stack: Python 3.12, Streamlit, numpy, httpx (odds only).

**Known deferred items:** Phase 6 Full-Major v3 (Stages 2–3 + playoffs) → next milestone; Phase 5 live-slug `/browse` checkpoint pending Cologne market posting; [INFERRED] Cologne seeds pending official confirmation; 2 cosmetic audit warnings (Ballot A UI label, stale STATE.md GATE entry).

---
