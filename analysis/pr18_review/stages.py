import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from valve_parse import matches, standings, REPO

def component(ms, anchor):
    adj = collections.defaultdict(set)
    for m in ms: adj[m["winner"]].add(m["loser"]); adj[m["loser"]].add(m["winner"])
    seen, stack = {anchor}, [anchor]
    while stack:
        for v in adj[stack.pop()]:
            if v not in seen: seen.add(v); stack.append(v)
    return seen

# (event, stage, details dir, first day, last day, anchor team, pre-stage standings file)
SPEC = [
 ("Austin 2025", 1, "live/2025/details/2025_07_07", "2025-06-03", "2025-06-06", "B8", "live/2025/standings_global_2025_06_02.md"),
 ("Austin 2025", 2, "live/2025/details/2025_07_07", "2025-06-07", "2025-06-10", "FaZe", "live/2025/standings_global_2025_06_02.md"),
 ("Austin 2025", 3, "live/2025/details/2025_07_07", "2025-06-12", "2025-06-15", "Vitality", "live/2025/standings_global_2025_06_02.md"),
 ("Budapest 2025", 1, "live/2026/details/2026_01_05", "2025-11-24", "2025-11-27", "FaZe", "live/2025/standings_global_2025_11_03.md"),
 ("Budapest 2025", 2, "live/2026/details/2026_01_05", "2025-11-29", "2025-12-02", "Aurora", "live/2025/standings_global_2025_11_03.md"),
 ("Budapest 2025", 3, "live/2026/details/2026_01_05", "2025-12-04", "2025-12-07", "Vitality", "live/2025/standings_global_2025_12_01.md"),
 ("Cologne 2026", 1, "live/2026/details/2026_07_06", "2026-06-02", "2026-06-05", "Liquid", "live/2026/standings_global_2026_06_01.md"),
 ("Cologne 2026", 2, "live/2026/details/2026_07_06", "2026-06-06", "2026-06-09", "Spirit", "live/2026/standings_global_2026_06_01.md"),
 ("Cologne 2026", 3, "live/2026/details/2026_07_06", "2026-06-11", "2026-06-15", "Vitality", "live/2026/standings_global_2026_06_01.md"),
]
_cache = {}
def load(spec):
    ev, st, d, lo, hi, anchor, sfile = spec
    if d not in _cache: _cache[d] = matches(os.path.join(REPO, d))
    ms = [m for m in _cache[d].values() if lo <= m["date"] <= hi]
    comp = component(ms, anchor)
    ms = sorted((m for m in ms if m["winner"] in comp), key=lambda m: (m["date"], -m["id"]))
    return ms, comp, standings(os.path.join(REPO, sfile))

if __name__ == "__main__":
    for spec in SPEC:
        ms, comp, st = load(spec)
        days = collections.Counter(m["date"] for m in ms)
        missing = [t for t in comp if t not in st]
        print(spec[0], "S%d" % spec[1], "teams", len(comp), "matches", len(ms), dict(sorted(days.items())), "no-rating:", missing)
        if len(comp) != 16 or len(ms) != 33: print("   teams:", sorted(comp))
