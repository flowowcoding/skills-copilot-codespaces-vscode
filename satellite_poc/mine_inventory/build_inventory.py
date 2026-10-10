#!/usr/bin/env python3
"""Build a named, commodity-tagged inventory of mines with real footprint polygons.

Joins three free datasets:

* ICMM Global Mining Dataset (Sep 2025, V1, CC BY 4.0): names, coordinates,
  commodities, asset type, confidence. Public release = 8,508 assets.
  https://www.icmm.com/website/data/2025/global-mining-dataset.xlsx
* Maus et al. (2022) Global-scale mining polygons v2 (PANGAEA 942325, CC BY-SA 4.0):
  44,929 hand-digitised mining-land polygons (pits, dumps, tailings, ponds, plant).
  https://download.pangaea.de/dataset/942325/files/global_mining_polygons_v2.gpkg
* Jasansky et al. "Global ML-ready dataset for mining areas" (Zenodo 14195737):
  1,514 Sentinel-2 tiles with preferred polygons (Maus or Tang et al. 2023) and a
  manual mine-type label (Surface / Placer / Brine & Evaporation Pond / Underground).

Method
------
1. ICMM: keep rows whose Asset Type contains "Mine" and that have valid coordinates;
   normalise commodity names (strip/lower-case, merge synonyms, e.g. "thermal coal" ->
   coal, "chromite" -> chromium) while keeping the raw primary commodity.
2. Maus polygons are clustered: polygons closer than ``--cluster-m`` (default 500 m)
   are merged into one footprint (done per UTM zone, then a cross-zone merge pass).
3. Each ICMM mine point is matched to a cluster: point-in-polygon first, else nearest
   cluster within ``--max-dist-m`` (default 3 km), distance measured in the point's UTM
   zone. Points still unmatched are tried against the Zenodo preferred polygons
   (adds Tang et al. polygons not present in Maus).
4. Clusters that receive several ICMM points are flagged (``n_icmm_on_cluster`` > 1);
   such complexes are additionally partitioned by assigning each member polygon to its
   nearest ICMM point (``own_*`` columns and the ``mines_own`` layer).
5. Mine type comes from the Zenodo tile label where a Zenodo polygon overlaps the
   footprint, else from a small manual table (``manual_mine_type.csv``) for well-known
   mines, else "unknown". A polygon is NOT proof that a mine is surface-worked or active.

Outputs (in ``--out-dir``)
--------------------------
* ``mine_inventory.gpkg`` layers: ``mines`` (one row per ICMM mine; geometry = merged
  footprint cluster, null if unmatched), ``mines_own`` (partitioned footprint),
  ``clusters`` (unique footprints, deduplicated, with the ICMM names on each).
* ``mine_inventory.csv``: same attributes as ``mines`` plus bbox and a simplified WKT.
* ``summary_*.csv``: commodity x country counts, top commodities, Chile/Peru copper,
  lithium, sanity checks.

Usage
-----
    python -I build_inventory.py \\
        --icmm  .../icmm/global-mining-dataset.xlsx \\
        --maus  .../maus/global_mining_polygons_v2.gpkg \\
        --zenodo .../mining_area_data.gpkg \\
        --out-dir satellite_poc/mine_inventory \\
        [--gpkg-out /path/full_res.gpkg]
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import wkt as shp_wkt
from shapely.geometry import Point
from shapely.ops import unary_union

log = logging.getLogger("mine_inventory")
HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- commodities
COMMODITY_SYNONYMS = {
    "thermal coal": "coal", "metallurgical coal": "coal", "coking coal": "coal",
    "lignite": "coal", "anthracite": "coal",
    "iron": "iron ore", "steel": "iron ore",
    "chromite": "chromium", "ferrochrome": "chromium",
    "ferronickel": "nickel",
    "ferromanganese": "manganese", "ferrosilicon manganese": "manganese",
    "ferroniobium": "niobium",
    "aluminium": "bauxite", "aluminum": "bauxite", "alumina": "bauxite",
    "borates": "boron",
    "lanthanides": "rare earths", "rare earth elements": "rare earths", "ree": "rare earths",
    "ilmenite": "titanium", "rutile": "titanium", "heavy mineral sands": "mineral sands",
    "barite": "barium", "baryte": "barium",
    "diamonds": "diamond",
    "phosphate rock": "phosphate",
}
COAL_DETAIL = {"thermal coal", "metallurgical coal", "coal"}


def norm_commodity(s: str | float) -> str | None:
    if not isinstance(s, str):
        return None
    s = re.sub(r"\s+", " ", s.strip().lower())
    if not s or s == "nan":
        return None
    return COMMODITY_SYNONYMS.get(s, s)


def split_commodities(*vals) -> list[str]:
    out: list[str] = []
    for v in vals:
        if not isinstance(v, str):
            continue
        for tok in re.split(r"[;,/]", v):
            n = norm_commodity(tok)
            if n and n not in out:
                out.append(n)
    return out


# ---------------------------------------------------------------- geometry helpers
def utm_epsg(lon: float, lat: float) -> int:
    zone = int(np.clip(np.floor((lon + 180) / 6) + 1, 1, 60))
    return (32600 if lat >= 0 else 32700) + zone


class UnionFind:
    def __init__(self, n):
        self.p = np.arange(n)

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def cluster_polygons(polys: gpd.GeoDataFrame, cluster_m: float) -> np.ndarray:
    """Return a cluster label per polygon; polygons within ``cluster_m`` share a label."""
    n = len(polys)
    uf = UnionFind(n)
    rp = polys.geometry.representative_point()
    epsg = np.array([utm_epsg(p.x, p.y) for p in rp])
    for code in np.unique(epsg):
        idx = np.where(epsg == code)[0]
        g = polys.geometry.iloc[idx].to_crs(code).reset_index(drop=True)
        buf = g.buffer(cluster_m / 2.0, resolution=4)
        bdf = gpd.GeoDataFrame(geometry=buf, crs=code)
        pairs = gpd.sjoin(bdf, bdf, predicate="intersects", how="inner")
        for a, b in zip(pairs.index.values, pairs["index_right"].values):
            if a != b:
                uf.union(idx[a], idx[b])
    # cross-zone pass: polygons in different zones whose expanded bboxes touch
    deg = cluster_m / 111_000.0 * 3
    b = polys.geometry.bounds.values
    tree = polys.sindex
    for i in range(n):
        lat = (b[i, 1] + b[i, 3]) / 2
        dx = deg / max(np.cos(np.radians(lat)), 0.1)
        cand = tree.query(_box(b[i, 0] - dx, b[i, 1] - deg, b[i, 2] + dx, b[i, 3] + deg))
        for j in cand:
            if j <= i or epsg[j] == epsg[i]:
                continue
            gi = gpd.GeoSeries([polys.geometry.iloc[i], polys.geometry.iloc[j]], crs=4326).to_crs(epsg[i])
            if gi.iloc[0].distance(gi.iloc[1]) <= cluster_m:
                uf.union(i, j)
    return np.array([uf.find(i) for i in range(n)])


def _box(minx, miny, maxx, maxy):
    from shapely.geometry import box
    return box(minx, miny, maxx, maxy)


def area_km2(geom, epsg: int) -> float:
    return float(gpd.GeoSeries([geom], crs=4326).to_crs(epsg).area.iloc[0] / 1e6)


def build_clusters(polys: gpd.GeoDataFrame, labels: np.ndarray, id_col: str, prefix: str):
    polys = polys.copy()
    polys["_lab"] = labels
    rows = []
    for lab, grp in polys.groupby("_lab"):
        geom = unary_union(grp.geometry.values)
        c = geom.representative_point()
        code = utm_epsg(c.x, c.y)
        rows.append({
            "cluster_id": f"{prefix}{int(lab):05d}",
            "n_polygons": len(grp),
            "member_ids": ";".join(str(v) for v in grp[id_col].values),
            "iso3": grp["ISO3_CODE"].mode().iloc[0] if "ISO3_CODE" in grp else None,
            "utm_epsg": code,
            "footprint_km2": area_km2(geom, code),
            "geometry": geom,
        })
    cl = gpd.GeoDataFrame(rows, geometry="geometry", crs=4326)
    polys["cluster_id"] = [f"{prefix}{int(v):05d}" for v in labels]
    return cl, polys


def match_points(pts: gpd.GeoDataFrame, cl: gpd.GeoDataFrame, max_dist_m: float):
    """Point-in-polygon, else nearest cluster within max_dist_m (UTM distance)."""
    out = pd.DataFrame(index=pts.index, columns=["cluster_id", "method", "dist_m"], dtype=object)
    inside = gpd.sjoin(pts[["geometry"]], cl[["cluster_id", "footprint_km2", "geometry"]],
                       predicate="within", how="inner")
    # if a point falls in >1 cluster (overlapping fragments), keep the largest
    inside = inside.sort_values("footprint_km2", ascending=False)
    inside = inside[~inside.index.duplicated()]
    out.loc[inside.index, "cluster_id"] = inside["cluster_id"]
    out.loc[inside.index, "method"] = "inside"
    out.loc[inside.index, "dist_m"] = 0.0
    tree = cl.sindex
    deg = max_dist_m / 111_000.0 * 1.2
    for i in pts.index.difference(inside.index):
        p = pts.geometry.loc[i]
        dx = deg / max(np.cos(np.radians(p.y)), 0.05)
        cand = tree.query(_box(p.x - dx, p.y - deg, p.x + dx, p.y + deg))
        if len(cand) == 0:
            continue
        code = utm_epsg(p.x, p.y)
        sub = cl.iloc[cand]
        d = sub.geometry.to_crs(code).distance(gpd.GeoSeries([p], crs=4326).to_crs(code).iloc[0])
        j = d.values.argmin()
        if d.values[j] <= max_dist_m:
            out.loc[i, ["cluster_id", "method", "dist_m"]] = [sub["cluster_id"].iloc[j], "nearest", float(d.values[j])]
    return out


# ---------------------------------------------------------------- main build
def load_icmm(path: Path) -> gpd.GeoDataFrame:
    df = pd.read_excel(path, sheet_name="External")
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith("str"):
            df[c] = df[c].astype("string").str.strip()
    n0 = len(df)
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    is_mine = df["Asset Type"].fillna("").str.contains("Mine", case=False)
    ok = df["Latitude"].between(-90, 90) & df["Longitude"].between(-180, 180) & \
        ~((df["Latitude"] == 0) & (df["Longitude"] == 0))
    log.info("ICMM rows %d; mine asset types %d; with valid coords %d", n0, is_mine.sum(), (is_mine & ok).sum())
    df = df[is_mine & ok].copy()
    df["primary_commodity_raw"] = df["Primary Commodity"].str.lower()
    df["primary_commodity"] = df["Primary Commodity"].map(norm_commodity)
    df["secondary_commodity"] = df["Secondary Commodity"].map(norm_commodity)
    df["all_commodities"] = [";".join(split_commodities(a, b, c)) for a, b, c in
                             zip(df["Primary Commodity"], df["Secondary Commodity"], df["Other Commodities"])]
    df["coal_type"] = np.where(df["primary_commodity_raw"].isin(COAL_DETAIL), df["primary_commodity_raw"], None)
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]), crs=4326)
    return g.reset_index(drop=True)


def zenodo_layers(path: Path):
    tiles = gpd.read_file(path, layer="tiles")
    pref = gpd.read_file(path, layer="preferred_polygons")
    pref = pref.merge(tiles[["tile_id", "source_dataset", "preferred_dataset", "minetype1", "minetype2"]],
                      on="tile_id", how="left")
    pref = pref[(pref["source_dataset"] != "rejected") & pref.geometry.notna() & ~pref.geometry.is_empty]
    pref = pref.explode(index_parts=False).reset_index(drop=True)
    pref = pref[pref.geom_type == "Polygon"].reset_index(drop=True)
    return pref


def build(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    icmm = load_icmm(Path(args.icmm))

    maus = gpd.read_file(args.maus, layer="mining_polygons").to_crs(4326)
    maus = maus.reset_index(drop=True)
    maus["maus_fid"] = maus["FID"] if "FID" in maus else maus.index
    maus["geometry"] = maus.geometry.make_valid()
    log.info("Maus polygons: %d", len(maus))
    labels = cluster_polygons(maus, args.cluster_m)
    mcl, maus = build_clusters(maus, labels, "maus_fid", "M")
    log.info("Maus clusters (<=%.0f m): %d", args.cluster_m, len(mcl))

    m1 = match_points(icmm, mcl, args.max_dist_m)
    icmm["cluster_id"] = m1["cluster_id"]
    icmm["match_method"] = m1["method"]
    icmm["match_dist_m"] = pd.to_numeric(m1["dist_m"])
    icmm["polygon_source"] = np.where(icmm["cluster_id"].notna(), "maus_v2", None)

    # ---- Zenodo
    zp = zenodo_layers(Path(args.zenodo))
    zp["zfid"] = np.arange(len(zp))
    zl = cluster_polygons(zp, args.cluster_m)
    zcl, zp = build_clusters(zp.assign(ISO3_CODE=None), zl, "zfid", "Z")
    ztiles = zp.groupby("cluster_id").agg(
        tile_ids=("tile_id", lambda s: ";".join(sorted({str(int(v)) for v in s}))),
        minetype1=("minetype1", lambda s: s.mode().iloc[0]),
        minetype2=("minetype2", lambda s: s.mode().iloc[0]),
        pref=("preferred_dataset", lambda s: ";".join(sorted(set(s.astype(str))))),
    )
    zcl = zcl.merge(ztiles, left_on="cluster_id", right_index=True)
    un = icmm["cluster_id"].isna()
    m2 = match_points(icmm[un], zcl, args.max_dist_m)
    hit = m2["cluster_id"].notna()
    idx = m2.index[hit]
    icmm.loc[idx, "cluster_id"] = m2.loc[idx, "cluster_id"]
    icmm.loc[idx, "match_method"] = "zenodo_" + m2.loc[idx, "method"].astype(str)
    icmm.loc[idx, "match_dist_m"] = pd.to_numeric(m2.loc[idx, "dist_m"])
    icmm.loc[idx, "polygon_source"] = "zenodo_" + zcl.set_index("cluster_id").loc[m2.loc[idx, "cluster_id"], "pref"].values
    icmm["match_method"] = icmm["match_method"].fillna("unmatched")
    log.info("Matched to Maus: %d, extra via Zenodo: %d, unmatched: %d of %d",
             (icmm.polygon_source == "maus_v2").sum(), hit.sum(), icmm.cluster_id.isna().sum(), len(icmm))

    clusters = pd.concat([mcl, zcl.drop(columns=["tile_ids", "minetype1", "minetype2", "pref"])], ignore_index=True)
    clusters = gpd.GeoDataFrame(clusters, geometry="geometry", crs=4326)

    # Zenodo mine-type label for every footprint it overlaps
    zj = gpd.sjoin(clusters[["cluster_id", "geometry"]],
                   zcl[["tile_ids", "minetype1", "minetype2", "geometry"]], predicate="intersects")
    zj = zj.groupby("cluster_id").agg(zenodo_tile_ids=("tile_ids", lambda s: ";".join(sorted(set(";".join(s).split(";"))))),
                                      zenodo_minetype=("minetype1", lambda s: ";".join(sorted(set(s)))),
                                      zenodo_scale=("minetype2", lambda s: ";".join(sorted(set(s)))))
    clusters = clusters.merge(zj, left_on="cluster_id", right_index=True, how="left")

    # ---- ambiguity / sharing
    cnt = icmm.groupby("cluster_id").size()
    icmm["n_icmm_on_cluster"] = icmm["cluster_id"].map(cnt).fillna(0).astype(int)
    names = icmm.groupby("cluster_id")["Mine Name"].apply(lambda s: " | ".join(sorted(set(s.dropna()))))
    clusters["n_icmm"] = clusters["cluster_id"].map(cnt).fillna(0).astype(int)
    clusters["icmm_names"] = clusters["cluster_id"].map(names)
    clusters["icmm_ids"] = clusters["cluster_id"].map(icmm.groupby("cluster_id")["ICMMID"].apply(lambda s: ";".join(s)))
    prim = icmm.groupby("cluster_id")["primary_commodity"].agg(lambda s: s.mode().iloc[0] if s.notna().any() else None)
    clusters["primary_commodity"] = clusters["cluster_id"].map(prim)

    # ---- partition shared clusters: assign member polygons to nearest ICMM point
    members = pd.concat([maus[["cluster_id", "maus_fid", "geometry"]].rename(columns={"maus_fid": "mid"}),
                         zp[["cluster_id", "zfid", "geometry"]].rename(columns={"zfid": "mid"})], ignore_index=True)
    members = gpd.GeoDataFrame(members, geometry="geometry", crs=4326)
    own_geom, own_area = {}, {}
    for cid, grp in icmm[icmm.cluster_id.notna()].groupby("cluster_id"):
        if len(grp) == 1:
            continue
        mem = members[members.cluster_id == cid]
        code = clusters.loc[clusters.cluster_id == cid, "utm_epsg"].iloc[0]
        mp = mem.to_crs(code)
        pp = grp.to_crs(code)
        d = np.array([[g.distance(p) for p in pp.geometry] for g in mp.geometry])
        owner = d.argmin(axis=1)
        for k, ii in enumerate(grp.index):
            sel = mem.geometry.values[owner == k]
            if len(sel):
                gg = unary_union(sel)
                own_geom[ii] = gg
                own_area[ii] = area_km2(gg, code)
            else:
                own_geom[ii] = None
                own_area[ii] = 0.0

    # ---- mine type
    cmeta = clusters.set_index("cluster_id")
    icmm["footprint_km2"] = icmm["cluster_id"].map(cmeta["footprint_km2"])
    icmm["cluster_n_polygons"] = icmm["cluster_id"].map(cmeta["n_polygons"])
    icmm["source_polygon_ids"] = icmm["cluster_id"].map(cmeta["member_ids"])
    icmm["iso3"] = icmm["cluster_id"].map(cmeta["iso3"])
    icmm["zenodo_tile_ids"] = icmm["cluster_id"].map(cmeta["zenodo_tile_ids"])
    icmm["zenodo_minetype"] = icmm["cluster_id"].map(cmeta["zenodo_minetype"])
    icmm["mine_type"] = "unknown"
    icmm["mine_type_source"] = None
    zt = icmm["zenodo_minetype"].fillna("")
    single = zt.ne("") & ~zt.str.contains(";")
    icmm.loc[single, "mine_type"] = zt[single].map(
        {"Surface": "surface", "Placer": "placer", "Underground": "underground",
         "Brine & Evaporation Pond": "brine"})
    icmm.loc[single, "mine_type_source"] = "zenodo_tile_label"
    manual_path = Path(args.manual) if args.manual else HERE / "manual_mine_type.csv"
    if manual_path.exists():
        man = pd.read_csv(manual_path, comment="#")
        man = man.set_index("icmm_id")
        hitm = icmm["ICMMID"].isin(man.index)
        icmm.loc[hitm, "mine_type"] = icmm.loc[hitm, "ICMMID"].map(man["mine_type"])
        icmm.loc[hitm, "mine_type_source"] = "manual"
        log.info("Manual mine-type labels applied: %d", hitm.sum())
    icmm["is_lithium"] = icmm["all_commodities"].str.split(";").apply(lambda l: "lithium" in l)

    # ---- assemble output
    out = pd.DataFrame({
        "icmm_id": icmm["ICMMID"],
        "mine_name": icmm["Mine Name"],
        "alt_names": icmm["Group Names"],
        "company": None,  # not in public ICMM release
        "country": icmm["Country or Region"],
        "iso3": icmm["iso3"],
        "asset_type": icmm["Asset Type"],
        "icmm_confidence": icmm["Confidence Factor"],
        "primary_commodity": icmm["primary_commodity"],
        "primary_commodity_raw": icmm["primary_commodity_raw"],
        "secondary_commodity": icmm["secondary_commodity"],
        "all_commodities": icmm["all_commodities"],
        "coal_type": icmm["coal_type"],
        "facility_status": None,  # not in public ICMM release
        "mine_type": icmm["mine_type"],
        "mine_type_source": icmm["mine_type_source"],
        "icmm_lon": icmm.geometry.x.round(6),
        "icmm_lat": icmm.geometry.y.round(6),
        "match_method": icmm["match_method"],
        "match_dist_m": icmm["match_dist_m"].round(0),
        "polygon_source": icmm["polygon_source"],
        "cluster_id": icmm["cluster_id"],
        "cluster_n_polygons": icmm["cluster_n_polygons"],
        "n_icmm_on_cluster": icmm["n_icmm_on_cluster"],
        "shared_footprint": icmm["n_icmm_on_cluster"] > 1,
        "footprint_km2": icmm["footprint_km2"].round(4),
        "own_footprint_km2": pd.Series(own_area).reindex(icmm.index).round(4),
        "source_polygon_ids": icmm["source_polygon_ids"],
        "zenodo_tile_ids": icmm["zenodo_tile_ids"],
        "zenodo_minetype": icmm["zenodo_minetype"],
        "is_lithium": icmm["is_lithium"],
    })
    out.loc[~out["shared_footprint"] & out["cluster_id"].notna(), "own_footprint_km2"] = out["footprint_km2"]
    geom = icmm["cluster_id"].map(cmeta["geometry"])
    mines = gpd.GeoDataFrame(out, geometry=gpd.GeoSeries(geom.values, crs=4326), crs=4326)
    b = mines.geometry.bounds
    for c in ["minx", "miny", "maxx", "maxy"]:
        mines[f"bbox_{c}"] = b[c].round(5)
    mines["large_complex"] = mines["footprint_km2"] > args.large_km2

    own = mines.drop(columns="geometry").copy()
    og = [own_geom.get(i, g) for i, g in zip(icmm.index, geom.values)]
    own = gpd.GeoDataFrame(own, geometry=gpd.GeoSeries(og, crs=4326), crs=4326)

    gpkg = Path(args.gpkg_out) if args.gpkg_out else out_dir / "mine_inventory.gpkg"
    gpkg.parent.mkdir(parents=True, exist_ok=True)
    if gpkg.exists():
        gpkg.unlink()
    mines.to_file(gpkg, layer="mines", driver="GPKG")
    own.to_file(gpkg, layer="mines_own", driver="GPKG")
    clusters[clusters.n_icmm > 0].to_file(gpkg, layer="clusters", driver="GPKG")
    log.info("Wrote %s (%.1f MB)", gpkg, gpkg.stat().st_size / 1e6)

    csv = mines.drop(columns="geometry").copy()
    simp = mines.geometry.simplify(args.wkt_simplify_deg, preserve_topology=True)
    csv["geometry_wkt_simplified"] = [g.wkt if g is not None and not g.is_empty else None for g in
                                      simp.apply(lambda g: shp_wkt.loads(shp_wkt.dumps(g, rounding_precision=5)) if g is not None else None)]
    csv.to_csv(out_dir / "mine_inventory.csv", index=False)
    log.info("Wrote %s (%.1f MB)", out_dir / "mine_inventory.csv", (out_dir / "mine_inventory.csv").stat().st_size / 1e6)

    write_summaries(mines, out_dir, args)
    return mines


SANITY = [  # name, lon, lat (approximate pit centre; from public sources / author knowledge)
    ("Escondida", -69.07, -24.27),
    ("Chuquicamata", -68.90, -22.29),
    ("Bingham Canyon", -112.15, 40.52),
    ("Grasberg", 137.11, -4.05),
    ("Greenbushes", 116.06, -33.86),
    ("Cobre Panama", -80.65, 8.84),
    ("Collahuasi", -68.71, -20.97),
    ("Cerro Verde", -71.59, -16.53),
    ("Antamina", -77.05, -9.54),
    ("Los Pelambres", -70.49, -31.72),
    ("Toquepala", -70.61, -17.25),
    ("Las Bambas", -72.33, -14.07),
    ("Pilgangoora", 118.89, -21.03),
    ("Salar de Atacama (SQM)", -68.40, -23.55),
    ("Oyu Tolgoi", 106.86, 43.00),
]


def write_summaries(m: gpd.GeoDataFrame, out_dir: Path, args):
    mt = m[m.cluster_id.notna()]
    rates = pd.DataFrame({
        "n_icmm_mines": [len(m)],
        "matched_inside_maus": [(m.match_method == "inside").sum()],
        "matched_nearest_maus": [(m.match_method == "nearest").sum()],
        "matched_zenodo": [m.match_method.str.startswith("zenodo").sum()],
        "unmatched": [(m.match_method == "unmatched").sum()],
        "shared_footprint": [m.shared_footprint.sum()],
        "unique_footprints": [mt.cluster_id.nunique()],
    })
    rates["match_rate"] = 1 - rates.unmatched / rates.n_icmm_mines
    rates.to_csv(out_dir / "summary_match_rates.csv", index=False)
    log.info("\n%s", rates.T.to_string())
    bycom = m.groupby("primary_commodity").agg(n=("icmm_id", "size"),
                                               matched=("cluster_id", lambda s: s.notna().sum()),
                                               unique_footprints=("cluster_id", "nunique"),
                                               median_km2=("footprint_km2", "median")).sort_values("n", ascending=False)
    bycom["match_rate"] = (bycom.matched / bycom.n).round(3)
    bycom.to_csv(out_dir / "summary_by_commodity.csv")
    surf = mt[~mt.mine_type.isin(["underground"])]
    cc = surf.groupby(["primary_commodity", "country"]).size().rename("n_matched").reset_index()
    cc.sort_values(["primary_commodity", "n_matched"], ascending=[True, False]).to_csv(
        out_dir / "summary_commodity_country.csv", index=False)
    cols = ["icmm_id", "mine_name", "country", "primary_commodity", "all_commodities", "mine_type",
            "mine_type_source", "icmm_confidence", "match_method", "match_dist_m", "footprint_km2",
            "own_footprint_km2", "n_icmm_on_cluster", "cluster_id", "icmm_lon", "icmm_lat"]
    cu = m[m.country.isin(["Chile", "Peru"]) & m.all_commodities.str.split(";").apply(lambda l: "copper" in l)]
    cu.sort_values(["country", "footprint_km2"], ascending=[True, False])[cols].to_csv(
        out_dir / "summary_chile_peru_copper.csv", index=False)
    li = m[m.is_lithium]
    li.sort_values(["country", "mine_name"])[cols].to_csv(out_dir / "summary_lithium.csv", index=False)

    # sanity check against known mines
    rows = []
    for name, lon, lat in SANITY:
        p = Point(lon, lat)
        code = utm_epsg(lon, lat)
        pu = gpd.GeoSeries([p], crs=4326).to_crs(code).iloc[0]
        ptsu = gpd.GeoSeries(gpd.points_from_xy(m.icmm_lon, m.icmm_lat), crs=4326).to_crs(code)
        d = ptsu.distance(pu)
        j = d.values.argmin()
        r = m.iloc[j]
        g = r.geometry
        inpoly = bool(g is not None and not g.is_empty and g.contains(p))
        rows.append({"reference": name, "ref_lon": lon, "ref_lat": lat,
                     "nearest_icmm": r.mine_name, "icmm_id": r.icmm_id, "icmm_dist_km": round(d.values[j] / 1000, 2),
                     "match_method": r.match_method, "footprint_km2": r.footprint_km2,
                     "n_icmm_on_cluster": r.n_icmm_on_cluster,
                     "ref_point_inside_footprint": inpoly, "primary_commodity": r.primary_commodity})
    sc = pd.DataFrame(rows)
    sc.to_csv(out_dir / "summary_sanity_check.csv", index=False)
    log.info("\n%s", sc.to_string())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--icmm", required=True)
    ap.add_argument("--maus", required=True)
    ap.add_argument("--zenodo", required=True)
    ap.add_argument("--out-dir", default=str(HERE))
    ap.add_argument("--gpkg-out", default=None, help="full-resolution GeoPackage path (default out-dir)")
    ap.add_argument("--manual", default=None, help="manual mine-type CSV (icmm_id,mine_type,...)")
    ap.add_argument("--cluster-m", type=float, default=500.0)
    ap.add_argument("--max-dist-m", type=float, default=3000.0)
    ap.add_argument("--large-km2", type=float, default=100.0, help="flag footprints larger than this")
    ap.add_argument("--wkt-simplify-deg", type=float, default=0.0005)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    build(args)


if __name__ == "__main__":
    main()
