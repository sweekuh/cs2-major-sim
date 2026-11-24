import json, subprocess, time, sys, datetime as dt
def get(url):
    r = subprocess.run(['curl','-sS','--compressed','-m','40',url], capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except Exception: return None
def day_events(day):
    out, off = [], 0
    while True:
        d = get(f"https://gamma-api.polymarket.com/events?tag_id=100780&closed=true&end_date_min={day}T00:00:00Z&end_date_max={day}T23:59:59Z&limit=50&offset={off}")
        if not isinstance(d, list) or not d: break
        out += d; off += 50
        if len(d) < 50: break
    return out
name, key, d0, d1 = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
day = dt.date.fromisoformat(d0); evs = {}
while day <= dt.date.fromisoformat(d1):
    for e in day_events(day.isoformat()):
        if key in e['title'] and e['slug'].startswith('cs2-'): evs[e['slug']] = e
    day += dt.timedelta(days=1)
out = []
for e in evs.values():
    ms = [m for m in e['markets'] if m.get('sportsMarketType') == 'moneyline' and m.get('slug') == e['slug']]
    if len(ms) != 1: continue
    m = ms[0]; toks = json.loads(m['clobTokenIds']); gs = m.get('gameStartTime') or e.get('startTime')
    t0 = int(dt.datetime.fromisoformat(gs.replace(' ', 'T').replace('+00', '+00:00').replace('Z', '+00:00').replace('+00:00:00','+00:00')).timestamp())
    h = (get(f"https://clob.polymarket.com/prices-history?market={toks[0]}&startTs={t0-6*3600}&endTs={t0+60}&fidelity=1") or {}).get('history', [])
    pre = [x for x in h if x['t'] <= t0]
    out.append(dict(slug=e['slug'], title=e['title'], outcomes=json.loads(m['outcomes']), result=json.loads(m['outcomePrices']), start=gs,
                    vol=m.get('volumeNum'), close=(pre[-1]['p'] if pre else None), close_lag=(pre[-1]['t'] - t0 if pre else None)))
    time.sleep(0.1)
json.dump(out, open(f'{name}_market.json', 'w'), indent=1)
print(name, len(evs), 'events;', sum(o['close'] is not None for o in out), 'with pre-start price')
