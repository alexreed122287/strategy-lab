"""Re-anchor split-corrupted series in the brain cache.

Detects a single uniform discontinuity (split-shaped) and rescales every bar
BEFORE it so the series is on one price scale. Writes only when --apply.
"""
import pandas as pd, glob, os, sys, json, datetime
BRAIN=os.path.expanduser('~/Projects/market-data-brain')
RATIOS=[(0.5,'2:1'),(0.25,'4:1'),(1/3,'3:1'),(2.0,'1:2'),(3.0,'1:3'),(1/10,'10:1')]
apply='--apply' in sys.argv
found=[]
for p in sorted(glob.glob(f'{BRAIN}/daily/*.parquet')):
    sym=os.path.basename(p)[:-8]
    try: df=pd.read_parquet(p)
    except Exception: continue
    cl=df['close'].tolist(); dt=df['date'].astype(str).tolist()
    if len(cl)<50: continue
    for k in range(max(1,len(cl)-400),len(cl)):
        if cl[k-1]<=0: continue
        r=cl[k]/cl[k-1]
        hit=next((lab for target,lab in RATIOS if abs(r-target)/target<0.06), None)
        if not hit: continue
        v=df['volume'].tolist()
        vr=(v[k]/v[k-1]) if v[k-1] else 0
        # SPLIT vs BAD PRINT. A split REBASES the series: every later bar stays
        # on the new scale. A bad print is ONE bar out of line and the next bar
        # snaps back to the old scale. Treating MCD's 2026-08-03 print (68.32 on
        # volume 357, with 270.64 before and 268.34 after) as a 4:1 split would
        # have rescaled 2,156 bars of correct history by 0.25.
        persists = (k+1 < len(cl)) and abs(cl[k+1]/cl[k] - 1.0) < 0.25
        kind = 'split' if persists else 'BAD PRINT'
        found.append((sym,dt[k],round(100*(r-1),1),hit,round(vr,2),k,p,kind))
        break
print("%-7s %-12s %8s %-6s %8s  %s"%("SYM","DATE","MOVE%","RATIO","VOL x","VERDICT"))
for s,d,m,h,vr,k,p,kind in found: print("%-7s %-12s %8.1f %-6s %8.2f  %s"%(s,d,m,h,vr,kind))
if not apply:
    print("\n(dry run - pass --apply to rewrite)"); sys.exit()
log={}
for sym,d,m,h,vr,k,p,kind in found:
    if kind!='split':
        # A bad print is repaired by removing the bar, not by rescaling history.
        df=pd.read_parquet(p)
        df=df.drop(df.index[k]).reset_index(drop=True)
        df.to_parquet(p, index=False)
        log[sym]={"date":d,"action":"dropped bad print","close_was":round(pd.read_parquet(p)['close'].tolist()[k-1],2) if k>0 else None,"repaired":str(datetime.date.today())}
        print(f"dropped bad print {sym} @ {d}")
        continue
    df=pd.read_parquet(p)
    r=df['close'].tolist()[k]/df['close'].tolist()[k-1]
    for col in ('open','high','low','close'):
        vals=df[col].tolist()
        df[col]=[x*r for x in vals[:k]]+vals[k:]
    vv=df['volume'].tolist()
    df['volume']=[int(x/r) for x in vv[:k]]+vv[k:]
    df.to_parquet(p, index=False)
    log[sym]={"date":d,"ratio":round(r,6),"split":h,"repaired":str(datetime.date.today())}
    print(f"repaired {sym} x{r:.4f} at {d}")
mp=f'{BRAIN}/manifest.json'
man=json.load(open(mp)) if os.path.exists(mp) else {}
man.setdefault('rebased',{}).update(log)
json.dump(man, open(mp,'w'), indent=1)
print(f"manifest updated: {len(log)} names recorded under 'rebased'")
