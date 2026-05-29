"""UI layer for the Cologne 2026 Swiss MC app (Phase 2).

Pure, AppTest-free helpers extracted from app.py so the two correctness seams
(freeze_locked cache key, rating validation) and the CI-bar HTML are unit-testable
without driving the full Streamlit app. This package imports engine, NEVER the reverse
(functional-core purity, CLAUDE.md): app.py / ui/* depend on engine; engine/ stays clean.

  - ui.cache  — freeze_locked / freeze_ratings (hashable cache keys) + run_mc_cached
                (the @st.cache_data wrapper over the frozen engine.run_mc).
  - ui.state  — FIXED_SEED, Mode enum, session_state key constants, validate_ratings.
  - ui.render — ci_bar_html + number formatting (numeric-only, XSS-safe).

ui.state and ui.render import NO streamlit (so their pure functions test without AppTest);
ui.cache imports streamlit only for the @st.cache_data decorator.
"""
