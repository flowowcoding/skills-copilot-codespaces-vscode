import sys, numpy as np, pandas as pd
from PIL import Image
f, ref_end, out = sys.argv[1], sys.argv[2], sys.argv[3]
d=np.load(f); st=d["st"]; dates=pd.to_datetime(d["dates"])
valid=np.isfinite(st).mean((1,2))>0.9
st, dates = st[valid], dates[valid]
anom=st-np.nanmedian(st,axis=(1,2),keepdims=True)     # pixel minus scene median (K)
ref=np.nanmean(anom[dates<ref_end],0)
roi=ref>=np.nanpercentile(ref,97)
s=pd.Series(np.nanmean(anom[:,roi],1),index=dates)
print("scenes",len(s),"roi px",roi.sum())
print(s.groupby(dates.to_period("Q")).agg(["mean","count"]).round(1).T.to_string())
s.to_csv(out+".csv")
img=np.clip((ref+2)/12*255,0,255).astype(np.uint8); img=np.dstack([img,img,img]); img[roi]=[255,60,0]
Image.fromarray(img).resize((img.shape[1]*6,img.shape[0]*6),Image.NEAREST).save(out+"_map.png")
