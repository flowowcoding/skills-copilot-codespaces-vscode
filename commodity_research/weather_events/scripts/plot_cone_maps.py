"""Map the trigger-advisory cone against the production region, with NHC's published GIS cone overlay.

For each requested (storm_id, region): reconstructed 3-day / 5-day cone (compute_overlap.build_cone,
point-in-time radii), the NHC published 5-day cone for the same advisory (GIS archive,
https://www.nhc.noaa.gov/gis/forecast/archive/<id>_5day_<NNN>.zip, 2008+), OFCL forecast track, and
the HURDAT2 best track (hindsight, dashed). It also reports the area overlap (IoU) between the
reconstructed and published 5-day cones as a validation check.

Usage: python plot_cone_maps.py --scratch DIR --data ../data --out ../figures \
          --events AL112017:citrus AL092022:citrus AL092021:gulf_energy AL142024:citrus
"""
import argparse
import os
import subprocess
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute_overlap as co  # noqa: E402
from plotstyle import C, TEXT, MUTED, setup  # noqa: E402

GIS = "https://www.nhc.noaa.gov/gis/forecast/archive/{sid}_5day_{n:03d}.zip"


def nhc_cone(scratch, sid, init, guess):
    """Find the GIS advisory whose tau-0 VALIDTIME matches init; returns (cone gdf, advisory no)."""
    d = os.path.join(scratch, "gis")
    os.makedirs(d, exist_ok=True)
    key = init.strftime("%d/%H00")
    for n in sorted(range(max(1, guess - 8), guess + 9), key=lambda k: abs(k - guess)):
        f = os.path.join(d, f"{sid}_5day_{n:03d}.zip")
        if not os.path.exists(f):
            if subprocess.run(["curl", "-sS", "-f", "-o", f, GIS.format(sid=sid, n=n)]).returncode:
                if os.path.exists(f):
                    os.remove(f)
                continue
        try:
            pts = gpd.read_file(f"zip://{f}!{sid}-{n:03d}_5day_pts.shp")
        except Exception:
            continue
        if pts[pts.TAU == 0].VALIDTIME.iloc[0] == key:
            return gpd.read_file(f"zip://{f}!{sid}-{n:03d}_5day_pgn.shp").to_crs(4326), n
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--events", nargs="+", required=True)
    a = ap.parse_args()
    plt = setup()
    fwd = Transformer.from_crs(4326, co.PROJ, always_xy=True)
    inv = Transformer.from_crs(co.PROJ, 4326, always_xy=True)
    reg = gpd.read_file(os.path.join(a.data, "regions.geojson"))
    land = gpd.read_file(f"zip://{a.scratch}/geo/ne_50m_land.zip")
    states = gpd.read_file(f"zip://{a.scratch}/geo/cb_2022_us_state_5m.zip").to_crs(4326)
    rad = pd.read_csv(os.path.join(a.data, "cone_radii_nm.csv"), index_col=0)
    rad.columns = rad.columns.astype(int)
    ov = pd.read_csv(os.path.join(a.data, "forecast_overlap.csv"), parse_dates=["init"])
    ad = pd.read_csv(os.path.join(a.scratch, "atcf_filtered.csv.gz"), dtype={"init": str})
    ad["init_t"] = pd.to_datetime(ad.init, format="%Y%m%d%H")
    hd, names = co.read_hurdat(os.path.join(a.scratch, "hurdat2.txt"))
    b26, n26 = co.read_bdecks(os.path.join(a.scratch, "bdeck_2026"))
    bt = pd.concat([hd, b26])
    names.update(n26)
    val = []
    for item in a.events:
        sid, region = item.split(":")
        o = ov[(ov.storm_id == sid) & (ov.region == region)].sort_values("init")
        trig = o[o.cone72 & (o.vmax72 >= 64)].iloc[0]
        g = ad[(ad.storm_id == sid) & (ad.tech == "OFCL") & (ad.init_t == trig.init)].sort_values("tau")
        rr = rad.loc[trig.init.year].to_dict()
        cones = {}
        for h in (72, 120):
            c = co.build_cone(co.track_pts(g, h), rr, fwd)
            cones[h] = gpd.GeoSeries([c], crs=co.PROJ).to_crs(4326)
        ninit = ad[(ad.storm_id == sid) & (ad.tech == "OFCL")].init_t.drop_duplicates().sort_values()
        guess = int((ninit <= trig.init).sum())
        sl = sid[:2].lower() + sid[2:]
        nhc, advno = nhc_cone(a.scratch, sl, trig.init, guess) if trig.init.year >= 2008 else (None, None)
        fig, ax = plt.subplots(figsize=(7, 5.6))
        land.plot(ax=ax, color="#efeeea", edgecolor="#d9d8d3", linewidth=0.5)
        states.boundary.plot(ax=ax, color="#d9d8d3", linewidth=0.4)
        reg[reg.region == region].plot(ax=ax, color=C[2], alpha=0.55, edgecolor=C[2])
        cones[120].plot(ax=ax, facecolor="none", edgecolor=C[0], linewidth=1.2, linestyle=":")
        cones[72].plot(ax=ax, color=C[0], alpha=0.18, edgecolor=C[0], linewidth=1.2)
        if nhc is not None:
            nhc.boundary.plot(ax=ax, color=C[3], linewidth=1.3)
            A, B = nhc.to_crs(co.PROJ).geometry.iloc[0], cones[120].to_crs(co.PROJ).iloc[0]
            iou = A.intersection(B).area / A.union(B).area
            val.append(dict(storm_id=sid, name=names.get(sid), init=trig.init, nhc_adv=advno, iou_5day=round(iou, 3),
                            area_ratio=round(B.area / A.area, 3)))
        ax.plot(g.lon, g.lat, "-o", color=C[0], ms=3, lw=1.2)
        b = bt[bt.storm_id == sid]
        ax.plot(b.lon, b.lat, "--", color=C[1], lw=1.4)
        xmin, xmax = min(g.lon.min(), -98) - 1, max(g.lon.max(), -76) + 1
        ymin, ymax = min(g.lat.min(), 22) - 1, max(g.lat.max(), 33) + 1
        ax.set_xlim(max(xmin, -100), min(xmax, -60))
        ax.set_ylim(max(ymin, 12), min(ymax, 40))
        ax.set_aspect(1 / np.cos(np.radians(28)))
        ax.grid(False)
        t_txt = (trig.init + pd.Timedelta(hours=3)).strftime("%Y-%m-%d %H UTC")
        ax.set_title(f"{names.get(sid, sid)} ({sid[-4:]}): first hurricane-threat advisory for {region}, issued {t_txt}",
                     fontsize=9.5)
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        hd_ = [Patch(color=C[2], alpha=0.55, label=f"{region} region"),
               Patch(facecolor=C[0], alpha=0.25, label="3-day cone (rebuilt)"),
               Line2D([], [], color=C[0], ls=":", label="5-day cone (rebuilt)"),
               Line2D([], [], color=C[0], marker="o", ms=3, label="NHC official track forecast"),
               Line2D([], [], color=C[1], ls="--", label="best track (hindsight)")]
        if nhc is not None:
            hd_.insert(3, Line2D([], [], color=C[3], label=f"NHC published 5-day cone (adv {advno})"))
        ax.legend(handles=hd_, loc="lower left", fontsize=7.5)
        ax.tick_params(labelsize=7, colors=MUTED)
        fig.tight_layout()
        fn = os.path.join(a.out, f"cone_{names.get(sid, sid).lower()}{sid[-4:]}_{region}.png")
        fig.savefig(fn, dpi=130)
        plt.close(fig)
        print(fn)
    if val:
        pd.DataFrame(val).to_csv(os.path.join(a.data, "cone_validation.csv"), index=False)
        print(pd.DataFrame(val))


if __name__ == "__main__":
    main()
