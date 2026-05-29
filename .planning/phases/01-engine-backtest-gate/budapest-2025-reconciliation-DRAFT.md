# Budapest 2025 Stage 1 — reconciliation DRAFT (NOT yet frozen)

Source: liquipedia.net/counterstrike/StarLadder/2025/Major/Stage_1 (oldid 3296139), fetched via /browse 2026-05-29.
Status: RESULTS fully reconciled + internally consistent. SEEDS unresolved (see bottom) — do NOT freeze until seeds confirmed.

## Round-by-round results (winner in **bold**)

**R1 (Bo1):** **M80** def B8 13-11 · **Imperial** def RA 13-11 · **FLY** def Legacy 13-10 · **PV** def The Huns 13-8 · **Fluxo** def GL 13-10 · **NRG** def NIP 13-7 · **FaZe** def LVG 13-5 · **Fnatic** def RED 16-14
- 1-0: M80, Imperial, FLY, PV, Fluxo, NRG, FaZe, Fnatic
- 0-1: B8, RA, Legacy, The Huns, GL, NIP, LVG, RED

**R2 High (1-0, Bo1):** **FLY** def Imperial 13-6 · **M80** def PV 13-9 · **Fluxo** def Fnatic 13-9 · **NRG** def FaZe 13-10
**R2 Low (0-1, Bo1):** **Legacy** def RA 13-6 · **B8** def The Huns 13-11 · **RED** def GL 13-6 · **NIP** def LVG 13-2
- 2-0: FLY, M80, Fluxo, NRG
- 1-1 (the 8 entering R3 — anchor ✓): Imperial, PV, Fnatic, FaZe, Legacy, B8, RED, NIP
- 0-2: RA, The Huns, GL, LVG

**R3 High (2-0, Bo3):** **FLY** def Fluxo 2-0 (→3-0 ADV) · **M80** def NRG 2-0 (→3-0 ADV)
**R3 Mid (1-1, Bo1):** **Legacy** def RED 13-6 · **B8** def PV 13-11 · **Fnatic** def Imperial 13-3 · **NIP** def FaZe 13-8
**R3 Low (0-2, Bo3):** **GL** def RA 2-0 (RA →0-3 ELIM) · **The Huns** def LVG 2-0 (LVG →0-3 ELIM)
- 3-0 ADV: FLY, M80
- 2-1: Fluxo, NRG, Legacy, B8, Fnatic, NIP
- 1-2: RED, PV, Imperial, FaZe, GL, The Huns
- 0-3 ELIM: RA, LVG

**R4 High (2-1, Bo3):** **NIP** def Fluxo 2-0 (→3-1 ADV) · **B8** def Legacy 2-0 (→3-1 ADV) · **Fnatic** def NRG 2-1 (→3-1 ADV)
**R4 Low (1-2, Bo3):** **FaZe** def RED 2-1 (RED →1-3 ELIM) · **PV** def GL 2-0 (GL →1-3 ELIM) · **Imperial** def The Huns 2-0 (The Huns →1-3 ELIM)
- 3-1 ADV: NIP, B8, Fnatic
- 2-2: Fluxo, Legacy, NRG, FaZe, PV, Imperial
- 1-3 ELIM: RED, GL, The Huns

**R5 (2-2, Bo3):** **FaZe** def Fluxo 2-1 (→3-2 ADV; Fluxo →2-3 ELIM) · **Imperial** def NRG 2-0 (→3-2 ADV; NRG →2-3 ELIM) · **PV** def Legacy 2-1 (→3-2 ADV; Legacy →2-3 ELIM)

## Final standings (8 ADV / 8 ELIM — consistent ✓)
- 3-0: M80, FLY
- 3-1: B8, Fnatic, NIP
- 3-2: PV, Imperial, FaZe
- 2-3 ELIM: Fluxo, NRG, Legacy
- 1-3 ELIM: RED, GL, The Huns
- 0-3 ELIM: RA, LVG

Advancers = M80, FLY, B8, Fnatic, NIP, PV, Imperial, FaZe — matches the expected stable set EXACTLY ✓

## R1 seed pairs (each = {seed k, seed k+8}, k=1..8)
M80/B8 · Imperial/RA · FLY/Legacy · PV/The Huns · Fluxo/GL · NRG/NIP · FaZe/LVG · Fnatic/RED

## ⚠ UNRESOLVED: exact Valve seed integers (1-16) — and a real divergence

HLTV (user screenshots, 2026-05-29) gives VRS world ranks for the 16 teams. Sorted ascending:
1 Legacy(#8) · 2 B8(#16) · 3 FaZe(#17) · 4 GamerLegion(#20) · 5 PARIVISION(#22) · 6 fnatic(#24) ·
7 FlyQuest(#25) · 8 M80(#26) · 9 NIP(#28) · 10 Lynn Vision(#29) · 11 NRG(#30) · 12 Imperial(#33) ·
13 Fluxo(#39) · 14 Rare Atom(#56) · 15 The Huns(#62) · 16 RED Canids(#65)
(The per-card orange VRS badges give a slightly different order, e.g. FlyQuest seed-time #44.)

**BLOCKER — the observed pairings do NOT reduce to our engine's rules under this seed order:**
- R1 actual: M80–B8, Imperial–RA, FLY–Legacy, PV–The Huns, Fluxo–GL, NRG–NIP, FaZe–LVG, Fnatic–RED.
  Under seeds above, N-vs-N+8 would give Legacy–NIP, B8–LVG, FaZe–NRG, … — completely different.
  (1-v-16 high/low fold also doesn't match.) So Budapest R1 ≠ a simple seed-offset under VRS order.
- R2 "High" (8 R1-winners, no rematch possible, uniform Buchholz → should be a pure seed fold):
  actual FLY–Imperial, M80–PV, Fnatic–Fluxo, FaZe–NRG. Neither the world-rank order nor the orange
  order reproduces this fold (only Fnatic–Fluxo coincidentally matches under one).

**Implication:** either (a) Budapest's published seed integers differ from both HLTV rankings I can
see, or (b) Valve's within-group pairing has a nuance our engine's fold doesn't capture. I cannot
disentangle (a) from (b) without the authoritative Valve seed bracket — and that ambiguity is exactly
why I must NOT assert a green backtest on a guessed seeding (would be a false pass/fail; threat T-04-01).
The full Budapest pairing-reproduction backtest (GATE-01) is BLOCKED on authoritative seed data.
