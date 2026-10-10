"""Before/after statistics for the three halted mines. Usage: halt_stats.py RESULTS_DIR"""
import sys, pandas as pd
for name, halt in [("cobre","2023-11-24"),("eagle","2024-06-24"),("copler","2024-02-13")]:
    x=pd.read_csv(f"{sys.argv[1]}/{name}_activity.csv",index_col=0,parse_dates=True).activity*100
    h=pd.Timestamp(halt); pre=x[:h-pd.Timedelta(days=30)]; post=x[h+pd.Timedelta(days=30):]
    d=(pre.mean()-post.mean())/((pre.var()+post.var())/2)**.5
    # same calendar months only, to remove seasonality
    pm=pre.groupby(pre.index.month).mean(); qm=post.groupby(post.index.month).mean(); both=pm.index.intersection(qm.index)
    print(f"{name:7s} pre {pre.mean():+.1f} post {post.mean():+.1f}  separation d={d:.1f}  same-month gap {(pm[both]-qm[both]).mean():+.1f} pts, positive in {(pm[both]>qm[both]).sum()}/{len(both)} months")
    r=x.rolling(5,center=True).median()
    print("   5-pass median by quarter:", r.groupby(r.index.to_period('Q')).mean().round(1).to_dict())
