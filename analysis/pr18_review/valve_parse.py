"""Parse Valve regional-standings detail files into a series-level match list + standings tables."""
import re, glob, os, json, collections
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "valve", "repo")

def standings(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if m:
            out.setdefault(m.group(3), (int(m.group(1)), int(m.group(2)), m.group(4)))  # first (best) roster per name
    return out

def matches(details_dir):
    """Return {match_id: dict(date, winner, loser)} by joining both teams' rows on Match ID."""
    rows = collections.defaultdict(list)
    for f in glob.glob(os.path.join(details_dir, "*.md")):
        txt = open(f, encoding="utf-8").read()
        name = re.search(r"Team Name: (.+?)<br", txt).group(1).strip()
        for m in re.finditer(r"^\|\s*\d+\s*\|\s*(\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*\|\s*([WL])\s*\|", txt, re.M):
            rows[int(m.group(1))].append((m.group(2), name, m.group(3).strip(), m.group(4)))
    out = {}
    for mid, rs in rows.items():
        date, name, opp, wl = rs[0]
        w, l = (name, opp) if wl == "W" else (opp, name)
        out[mid] = dict(id=mid, date=date, winner=w, loser=l, n_rows=len(rs))
    return out

if __name__ == "__main__":
    import sys
    d = sys.argv[1]; lo, hi = sys.argv[2], sys.argv[3]
    ms = [m for m in matches(os.path.join(REPO, d)).values() if lo <= m["date"] <= hi]
    by = collections.Counter(m["date"] for m in ms)
    print(len(ms), sorted(by.items()))
