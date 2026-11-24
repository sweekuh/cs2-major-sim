"""Fetch Cologne match + qualify-market price histories (1-minute) for the derivative backtest."""
import json, subprocess, sys, time, datetime as dt
def get(u):
    for i in range(4):
        r=subprocess.run(['curl','-sS','--compressed','-m','60',u],capture_output=True,text=True)
        try: return json.loads(r.stdout)
        except Exception: time.sleep(2*(i+1))
    return None
def ts(s): return int(dt.datetime.fromisoformat(s.replace(' ','T').replace('+00','+00:00').replace('Z','+00:00').replace('+00:00:00','+00:00')).timestamp())
def history(tok, t0, t1):
    pts={}
    t=t0
    while t<t1:
        e=min(t1,t+2*86400)
        h=get(f'https://clob.polymarket.com/prices-history?market={tok}&startTs={t}&endTs={e}&fidelity=1') or {}
        for p in h.get('history',[]): pts[p['t']]=p['p']
        t=e
    return sorted(pts.items())
out={'matches':[], 'qualify':{}}
mk=json.load(open(sys.argv[1]))  # cologne_market.json summaries (slug, title, start)
for m in mk:
    st=int(m['title'].split('Stage ')[-1][0])
    if st not in (1,2): continue
    ev=get(f'https://gamma-api.polymarket.com/events?slug={m["slug"]}')
    e=ev[0]; mm=[x for x in e['markets'] if x.get('sportsMarketType')=='moneyline' and x.get('slug')==e['slug']][0]
    toks=json.loads(mm['clobTokenIds']); outs=json.loads(mm['outcomes'])
    t0=ts(mm.get('gameStartTime') or e['startTime'])
    hist=history(toks[0], t0-36*3600, t0+8*3600)
    out['matches'].append({'slug':m['slug'],'stage':st,'outcomes':outs,'start':t0,'result':json.loads(mm['outcomePrices']),'created':ts(mm['createdAt']),'hist':hist})
    print('match',m['slug'],len(hist),flush=True)
for slug,stage in (('iem-cologne-major-2026-qualify-to-stage-2',1),('iem-cologne-major-2026-qualify-to-stage-3',2)):
    e=get(f'https://gamma-api.polymarket.com/events?slug={slug}')[0]
    rows=[]
    for x in e['markets']:
        tok=json.loads(x['clobTokenIds'])[0]
        t0=ts(x['createdAt'])-60; t1=t0+8*86400
        hist=history(tok,t0,t1)
        rows.append({'team':x['groupItemTitle'],'result':json.loads(x['outcomePrices']),'created':ts(x['createdAt']),'volume':float(x.get('volumeNum') or 0),'hist':hist})
        print('qualify',stage,x['groupItemTitle'],len(hist),flush=True)
    out['qualify'][stage]=rows
json.dump(out,open('cologne_bt_data.json','w'))
print('done', len(out['matches']), 'matches')
