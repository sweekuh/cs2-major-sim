"""Goals-based World Cup fair-value engine (Dixon-Coles match model + tournament Monte Carlo).

This package replaces the CS2 Swiss engine for soccer. v1 ships the team model and (Phase 1+)
a bivariate-Poisson match model calibrated to de-vigged sharp 1X2, a 12-group round-robin with
FIFA tiebreakers, a 32-team knockout bracket, and a market-pricing layer that prices any Kalshi
World Cup market off one retained Monte Carlo sample.
"""
