"""Read-only Kalshi World Cup edge monitor: fees, ranking, signal log + CLV, orchestration.

This package is the headless monitor layer. It depends on the pure ``odds`` ensemble and the
``engine.soccer`` fair-value engine, and emits costed, ranked edge signals. It does NOT place
orders (execution is a later, legally-gated phase).
"""
