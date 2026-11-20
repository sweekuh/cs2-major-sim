"""Criterion (c): replay real Major Swiss stages through the shipped engine; compare generated pairings with Valve's match record."""
import os, sys, json, collections
import numpy as np
SP = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, SP); sys.path.insert(0, ".")
from valve_parse import standings, REPO
from engine.swiss import simulate_stage
from engine.teams import Team
from engine.seeding import seed_next_stage, InvitedTeam

rows = json.load(open(os.path.join(SP, "major_swiss_matches.json")))
SEED_FILES = {"Austin 2025": ["invitation/2025/standings_global_2025_05_05.md", "invitation/2025/standings_global_2025_06_02.md", "invitation/2025/standings_global_2025_04_07.md"],
              "Budapest 2025": ["invitation/2025/standings_global_2025_11_03.md", "invitation/2025/standings_global_2025_10_06.md"],
              "Cologne 2026": ["invitation/2026/standings_global_2026_06_01.md", "invitation/2026/standings_global_2026_05_04.md"]}

def stage_rows(ev, st): return [r for r in rows if r["event"] == ev and r["stage"] == st]
def actual_rounds(rs):
    out = collections.defaultdict(set)
    for r in rs: out[r["round"]].add(frozenset((r["a"], r["b"])))
    return out
def replay(teams, rs):
    """teams: seed-ordered Team list. Returns (per-round match flags, finals)."""
    idn = {t.name: t.id for t in teams}; nm = {t.id: t.name for t in teams}
    locked = {frozenset((idn[r["a"]], idn[r["b"]])): idn[r["a"] if r["y"] else r["b"]] for r in rs}
    po = []
    fin = simulate_stage([Team(t.id, t.name, t.seed, t.rating) for t in teams], None, 400.0, np.random.default_rng(0), locked, pairings_out=po)
    act = actual_rounds(rs); res = []
    for k, pairs in enumerate(po, 1):
        gen = {frozenset(nm[i] for i in p) for p in pairs}
        res.append((k, len(gen & act.get(k, set())), len(act.get(k, set()))))
    return res, fin

summary = []
for ev, files in SEED_FILES.items():
    prev_fin = None; chosen = None
    for st in (1, 2, 3):
        rs = stage_rows(ev, st); names = sorted({r["a"] for r in rs} | {r["b"] for r in rs})
        best = None
        for f in ([chosen] if chosen else files):
            sd = standings(os.path.join(REPO, f))
            if any(n not in sd for n in names): continue
            if st == 1:
                order = sorted(names, key=lambda n: sd[n][0])
                teams = [Team(i + 1, n, i + 1, float(sd[n][1])) for i, n in enumerate(order)]
            else:
                adv = {t.name for t in prev_fin.values() if t.wins == 3}
                invited = [InvitedTeam(n, sd[n][0], float(sd[n][1])) for n in names if n not in adv]
                assert len(invited) == 8 and adv <= set(names), (ev, st, len(invited))
                teams = seed_next_stage(prev_fin, invited)
            res, fin = replay(teams, rs)
            score = sum(a for _, a, _ in res)
            if best is None or score > best[0]: best = (score, f, res, fin, teams)
        score, f, res, fin, teams = best
        if st == 1: chosen = f
        prev_fin = fin
        r25 = sum(a for k, a, _ in res if k >= 2); t25 = sum(b for k, _, b in res if k >= 2)
        print(f"{ev} S{st} seeds from {os.path.basename(f)}: " + " ".join(f"R{k} {a}/{b}" for k, a, b in res) + f"  | rounds 2-5: {r25}/{t25}")
        summary.append((ev, st, res[0][1], r25, t25))
        if score < 33:
            print("   seeds:", [t.name for t in teams])
print("\nTOTAL rounds 2-5 pairings reproduced: %d/%d across %d stages; stages fully reproduced: %d" % (sum(s[3] for s in summary), sum(s[4] for s in summary), len(summary), sum(s[2] == 8 and s[3] == s[4] for s in summary)))
