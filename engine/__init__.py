"""swiss-mc engine — pure, dependency-free compute core.

This package MUST NOT import streamlit, httpx, or requests (Anti-Pattern 6):
the functional-core invariant is what makes the Phase 1 backtest gate possible.
"""
