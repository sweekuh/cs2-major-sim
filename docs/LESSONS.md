# Lessons — building a CS2 Major simulator where correctness is the product

This is the honest write-up of what it took to make a probability simulator I'd actually trust
enough to post predictions publicly. The simulator part was the easy half. The hard half was
making sure the numbers were *right*, because a probability tool that's confidently wrong is worse
than no tool at all.

If you only read one section, read "The two bugs that would have embarrassed me."

## What this is

A Monte-Carlo simulator for the IEM Cologne 2026 CS2 Swiss stage: per-team P(3-0)/advance/0-3,
market-anchored ratings, and the math-optimal 2/6/2 Pick'Em ballot with true coin odds P(≥5/10).
Live odds come from a market-odds ensemble (OddsPapi/Pinnacle + Kalshi), back-solved into ratings.

## The thesis: correctness is the product

The fun parts (a Swiss engine, a Streamlit UI, a Pick'Em optimizer) are table stakes. Anyone can
make a sim that *outputs* probabilities. The actual value is whether those probabilities are
trustworthy enough to bet a coin on. That reframes the whole project: the dashboard is the demo,
the test suite and the validation gate are the product.

Two design rules fell out of that and earned their keep:

1. **A hard backtest gate.** The engine has to reproduce a *real* past Major's Swiss pairings
   exactly (StarLadder Budapest 2025, rounds 1–5). Invariant tests (probabilities sum to 8/2/2)
   pass even when the pairing logic is subtly wrong, so they're not enough. The backtest is the
   only check that actually fails when the engine is broken. It stays green or the build is red.

2. **Show uncertainty, never hide it.** Every probability renders with a confidence band. When
   two odds sources disagree, the band visibly widens (a separate "epistemic" tone). The UI is
   built so it's physically hard to present false precision.

## The two bugs that would have embarrassed me

Both were *latent* until live odds turned on, and both produced plausible-looking output. That's
the dangerous kind: no crash, no stack trace, just wrong numbers.

### Bug 1 — every probability inflated ~12×

Under live odds the engine runs an epistemic outer loop: K=12 Beta-perturbed draws to capture
source disagreement. It tallied outcomes over all K×N simulations but normalized the point
probabilities by N, not K×N. So `P(advance)` for the favorite came out as **1193.5%**.

Three things make this a good war story:
- It was **invisible in rating-only mode** (K=1, so K×N == N). Every existing test and the
  backtest gate were rating-only, so the suite stayed green. The bug only existed on the exact
  code path the whole "live odds" feature depended on.
- It had been **fixed once and silently reverted.** A prior commit fixed it (`Result.n =
  len(sample)`) with a regression test; a later "two-tone CI band" commit reverted both the
  one-line fix and its test. The bug walked right back in.
- It was caught **by a screenshot**, not a test. I rendered the populated table to check it
  looked good for a Reddit post and saw "1193.5%." If I'd trusted the green suite, I'd have
  posted a table of three-digit percentages.

Fix: normalize by `len(sample)` (== K×N always, == N in rating-only so the backtest stays
byte-identical), plus a regression test that asserts the structural invariant `Σ P(advance) == 8`
and `max ≤ 1` *under* `var > 0`. That test fails the moment someone reverts the fix again.

### Bug 2 — the advance-pick rule (the 30-point number)

The in-game Pick'Em scores an "advance" pick as correct **only on a 3-1 or 3-2 finish**. A 3-0
goes in the separate 3-0 bucket. The optimizer scored an advance pick as `wins >= 3`, which
double-counts the 3-0 teams in the advance bucket. Result: the headline coin odds read **~90%**
when the honest number is **~59%**. Posting "90% to hit 5/10" would have been a 30-point lie.

The fix is one line (`is_adv = (wins == 3) & (losses >= 1)`), but the interesting part is the
scope discipline: the *per-team "who qualifies" display* genuinely should stay `wins >= 3` (a 3-0
team did qualify), while the *pick-scoring* must be 3-1/3-2. Two different questions, two code
paths, kept separate on purpose.

## The meta-lesson: green tests ≠ correct

Both bugs survived a green suite because the tests checked the wrong thing. The invariant tests
asserted band *width*, never that a probability was `≤ 1`. The optimizer fixtures happened to
never let an advance-picked team finish 3-0, so the old and new rules gave identical numbers on
the existing tests.

The rule I'd tattoo on the next project: **a regression test must fail when you apply the wrong
rule.** If you can revert the fix and the test still passes, it's decoration. For both bugs I
added tests by literally reverting the fix and confirming the test went red. An independent
code-review pass did the same revert-and-check, which is the right bar.

## The odds integration was a "probe first" exercise

The recorded API fixtures shipped with the repo were all marked `[ASSUMED — verify once markets
post]`, and every one of them was wrong about the real response shape. Lessons:

- **Don't build parsers against guessed shapes.** The first useful move was a throwaway probe
  script that hit the live keyless endpoints and printed the actual JSON. Kalshi's real fields
  (`yes_sub_title`, `yes_bid_dollars`, opponent parsed out of the market title) looked nothing
  like the assumed `team_a`/`team_b`/cents shape.
- **Discovery beats assumptions.** The live data also handed me the answer to a separate problem:
  the actual Round 1 bracket on Kalshi let me verify the inferred seeds against ground truth.
- **Drop sources that don't earn their place.** Polymarket was in the design as a third provider;
  its CS2 coverage turned out to be novelty futures ("will s1mple retire?"), no per-match markets.
  Cut it rather than carry dead weight.
- **Secrets leak through the boring path.** httpx logs the full request URL at INFO, including the
  `?apiKey=` query param. The key showed up in fetch logs until I forced the logger to WARNING.
  The fix is trivial; noticing it is the job.
- **Respect rate limits as a feature, not an afterthought.** OddsPapi's free tier 429'd on a burst
  of per-fixture calls; a 2s throttle + 429 retry turned a half-populated cache into a complete
  one.

## What I'd do differently

- **Co-locate a fix with the test that proves it.** Bug 1 came back because the one-line fix and
  its only guard lived in different files; a "tidy-up" commit reverted both. Now the *why* lives
  in a comment at the fix site, so a future revert reads as obviously wrong in review.
- **Gate on probability invariants in CI, not just band width.** `Σ P == 8/2/2` and `max ≤ 1`
  are cheap, total, and would have caught Bug 1 on day one.
- **Design the high-N path up front.** The optimizer needs the full per-sim sample, so memory
  grows with K×N. A 1M odds-fed run wants ~11 GB and OOMs. Probabilities converge by ~100k, so it
  never mattered in practice, but a streaming/aggregate sample would remove the footgun entirely.
- **Build the live fetch early behind a probe.** Stubbing it with `[ASSUMED]` fixtures let the
  guessed shapes rot until crunch time. A day-one probe against the real (even pre-event) API
  would have surfaced the shape mismatches when there was no clock running.
- **Make the rules single-source.** The advance-pick 3-1/3-2 rule was written down in a project
  note before the engine enforced it. The note and the code disagreed for a while. The rule
  should live in exactly one place the code reads.

## What process actually helped

- **Planning artifacts that encode decisions.** A phased planning trail plus short decision notes
  (e.g. "advance pick scores on 3-1/3-2, not 3-0"; "the n=N inflation, fixed, watch for reverts")
  are what flagged both bugs as known risks. Cheap to write, paid for themselves twice.
- **Adversarial review with a revert check.** Having a second pass independently reproduce the
  result and try to break the fix (revert it, confirm the test fails) is worth more than a dozen
  "looks good to me" reviews.
- **Screenshot the real output before you trust it.** The green suite said ship. The screenshot
  said 1193%. Render the thing a user will actually see.

## Honest scorecard

**Works and validated:** Swiss engine (backtest-gated), per-team probabilities with two-tone CI
bands, live OddsPapi + Kalshi ensemble, market-anchored ratings, 2/6/2 optimizer with correct
3-1/3-2 scoring and P(≥5) hill-climb, conditional re-sim live mode, 128 passing tests.

**Deferred (see `TODOS.md`):** the playoff Pick'Em optimizer (a different 7-pick round-weighted
ballot), a cron-fed odds cache so fetch lives outside the app, and a streaming sample path for
arbitrarily high N.

The thing I'm proudest of isn't a feature. It's that the two numbers I'd have posted publicly
(P(advance) and P(≥5)) were both wrong in ways that looked right, and the project's structure
caught both before they shipped.
