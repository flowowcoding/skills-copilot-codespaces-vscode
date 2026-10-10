"""Render the candidate sample pixels over state outlines (visual check of the mask).
Usage: python plot_mask.py [--season-mask <work>/mask_<season>.csv]  -> figures/mask_samples.png"""
import argparse, json, os
import pandas as pd
from plotstyle import setup, C, TEXT, MUTED
from shapely.geometry import shape
from shapely.ops import unary_union
HERE = os.path.dirname(os.path.abspath(__file__))
STATES = ["MT", "PR", "RS", "GO", "MS", "BA", "MG", "MA", "TO", "PI", "SP", "SC"]
ap = argparse.ArgumentParser(); ap.add_argument("--mask", default=None); ap.add_argument("--out", default=f"{HERE}/figures/mask_samples.png")
ap.add_argument("--title", default="Candidate MODIS 500 m sample pixels (soy municipalities, 40k per state)")
ap.add_argument("--validate-season", type=int, default=None, help="also write muni mask-share vs PAM-share check")
a = ap.parse_args()
plt = setup()
px = pd.read_csv(f"{HERE}/data/pixels.csv")
fig, ax = plt.subplots(figsize=(8, 8.5))
for st in STATES:
    fc = json.load(open(f"{HERE}/data/munis_{st}.geojson"))
    g = unary_union([shape(f["geometry"]).buffer(0.002) for f in fc["features"]])
    for p in getattr(g, "geoms", [g]):
        x, y = p.exterior.xy; ax.plot(x, y, color=MUTED, lw=0.6)
    ax.text(g.centroid.x, g.centroid.y, st, color=TEXT, fontsize=10, weight="bold", ha="center")
if a.mask:
    m = pd.read_csv(a.mask)
    ax.scatter(px.lon, px.lat, s=0.05, color="#d9d8d4", rasterized=True, label="candidate, not in mask")
    s = px[px.pixel_id.isin(m.pixel_id)]
    ax.scatter(s.lon, s.lat, s=0.08, color=C[0], rasterized=True, label="in season mask")
    ax.legend(markerscale=40, loc="lower right")
else:
    ax.scatter(px.lon, px.lat, s=0.05, color=C[0], rasterized=True)
ax.set_aspect(1.05); ax.set_title(a.title); ax.grid(False)
ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
fig.tight_layout(); fig.savefig(a.out, dpi=110)
if a.mask and a.validate_season:
    # municipal check: share of a municipality's sampled pixels in the mask vs PAM soy share (season's own PAM, i.e. ex post)
    import numpy as np
    m = pd.read_csv(a.mask); px["in"] = px.pixel_id.isin(m.pixel_id)
    g = px.groupby("muni").agg(frac=("in", "mean"), n=("in", "size"), state=("state", "first"))
    mu = pd.read_csv(f"{HERE}/data/pam_muni_area.csv"); A = mu[mu.year == a.validate_season].set_index("muni").area_ha
    from shapely.geometry import shape as shp
    from pyproj import Geod
    geod = Geod(ellps="WGS84"); area = {}
    for st in STATES:
        for f in json.load(open(f"{HERE}/data/munis_{st}.geojson"))["features"]:
            area[int(f["properties"]["codarea"])] = abs(geod.geometry_area_perimeter(shp(f["geometry"]))[0]) / 1e4
    g["pam_share"] = (A.reindex(g.index).fillna(0) / pd.Series(area).reindex(g.index)).clip(0, 1)
    g = g[g.n >= 30]
    r = g.groupby("state").apply(lambda d: pd.Series({"munis": len(d), "corr": np.corrcoef(d.frac, d.pam_share)[0, 1], "mean_mask_frac": d.frac.mean(), "mean_pam_share": d.pam_share.mean()}))
    r.loc["ALL"] = [len(g), np.corrcoef(g.frac, g.pam_share)[0, 1], g.frac.mean(), g.pam_share.mean()]
    r.round(3).to_csv(f"{HERE}/features/mask_validation_{a.validate_season}.csv"); print(r.round(2))
