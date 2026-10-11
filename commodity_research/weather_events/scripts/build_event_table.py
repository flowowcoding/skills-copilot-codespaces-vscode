"""Assemble the storm x region event table (one row per triggered storm-region pair).

Columns: storm, region, formation (first HURDAT2/b-deck tropical or subtropical fix), first NHC
advisory, first advisory whose 5-day cone touched the region, the pre-registered trigger (first 3-day
cone overlap with a forecast hurricane), the advisory when the centre came within 100 km
(point-in-time), the best-track closest approach and the nearest HURDAT2 landfall record (hindsight),
point-in-time and best-track hit flags, the matching damage report (data/damage_reports.csv), and
source URLs.

Usage: python build_event_table.py --scratch DIR --data ../data --results ../results
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute_overlap as co  # noqa: E402

SRC = ("forecasts: NHC ATCF a-deck OFCL https://ftp.nhc.noaa.gov/atcf/archive/{y}/a{sid}.dat.gz; "
       "best track: {bt}; advisory archive https://www.nhc.noaa.gov/archive/{y}/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--results", required=True)
    a = ap.parse_args()
    hd, names = co.read_hurdat(os.path.join(a.scratch, "hurdat2.txt"))
    b26, _ = co.read_bdecks(os.path.join(a.scratch, "bdeck_2026"))
    bt = pd.concat([hd, b26])
    form = bt[bt.status.isin(co.TC)].groupby("storm_id").time.min()
    adv = pd.read_csv(os.path.join(a.data, "advisories.csv.gz"), parse_dates=["init_t", "avail_utc"])
    first_adv = adv.groupby("storm_id").avail_utc.min()
    ov = pd.read_csv(os.path.join(a.data, "forecast_overlap.csv"), parse_dates=["init", "avail_utc"])
    ev = pd.read_csv(os.path.join(a.results, "events.csv"))
    dmg = pd.read_csv(os.path.join(a.data, "damage_reports.csv"))
    one = ev.drop_duplicates(["storm_id", "region"])
    rows = []
    for _, e in one.iterrows():
        o = ov[(ov.storm_id == e.storm_id) & (ov.region == e.region)]
        y = int(e.storm_id[-4:])
        hu_arr = o[(o.dist0_km <= 100) & (o.vmax0 >= 64)].avail_utc.min()
        d = dmg[(dmg.region == e.region) & (dmg.year == y) &
                dmg.storm.str.contains(str(e["name"]), case=False, na=False)]
        rows.append(dict(
            storm=f"{e['name']} {y}", storm_id=e.storm_id, region=e.region,
            markets=",".join(ev[(ev.storm_id == e.storm_id) & (ev.region == e.region)].market),
            sample=e["sample"], formation_utc=form.get(e.storm_id), first_advisory_utc=first_adv.get(e.storm_id),
            first_5day_cone_utc=(o[o.cone120].avail_utc.min()), trigger_3day_hurricane_utc=e.trigger_avail_utc,
            trigger_dist_km=e.trig_dist0_km, max_region_share_in_3day_cone=e.max_cone72_frac,
            max_gefs_share_within100km_72h=e.max_gefs_p72,
            hurricane_within100km_adv_utc=hu_arr, hit_point_in_time=e.hit_pit,
            besttrack_closest_utc=e.bt_t_closest, besttrack_min_dist_km=e.bt_dmin_km,
            besttrack_vmax_within100km_kt=e.bt_vmax_within100, besttrack_hurricane_hit=e.bt_hit_hu,
            nearest_landfall_utc=e.landfall_utc, nearest_landfall_vmax_kt=e.landfall_vmax,
            damage_report="; ".join(f"{m}: {v}" for m, v in zip(d.metric, d.value)),
            damage_source="; ".join(d.source),
            sources=SRC.format(y=y, sid=e.storm_id.lower(),
                               bt="https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-02272026.txt" if y < 2026
                               else "https://ftp.nhc.noaa.gov/atcf/btk/ (operational b-deck)")))
    t = pd.DataFrame(rows).sort_values(["region", "trigger_3day_hurricane_utc"])
    t.to_csv(os.path.join(a.data, "event_table.csv"), index=False)
    print(len(t), "storm-region events;", t.storm_id.nunique(), "storms")
    print(t.groupby(["region", "hit_point_in_time"]).size())


if __name__ == "__main__":
    main()
