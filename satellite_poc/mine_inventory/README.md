# Mine inventory: named mines with footprint polygons

A list of mines, each with a name, commodity and real footprint polygon, so the activity
index can run on many mines per commodity. Built by `build_inventory.py` (run `--help` for
the options). Rebuilding takes about 3 minutes.

```
python -I build_inventory.py \
  --icmm   <scratch>/mines/icmm/global-mining-dataset.xlsx \
  --maus   <scratch>/mines/maus/global_mining_polygons_v2.gpkg \
  --zenodo <scratch>/mines/mining_area_data.gpkg \
  --out-dir satellite_poc/mine_inventory
```

## Sources

| source | what it gives | licence | obtained |
|---|---|---|---|
| ICMM Global Mining Dataset, Sep 2025 V1 (`icmm.com/website/data/2025/global-mining-dataset.xlsx`) | names, aliases, coordinates, asset type, primary/secondary/other commodities, confidence | CC BY 4.0 | yes. The public file has **8,508 assets**, not ~15k: ICMM withheld 6,680 S&P-sourced assets. It has **no company, owner or status columns.** |
| Maus et al. 2022, global mining polygons v2 (PANGAEA [10.1594/PANGAEA.942325](https://doi.org/10.1594/PANGAEA.942325); file `download.pangaea.de/dataset/942325/files/global_mining_polygons_v2.gpkg`) | 44,929 hand-digitised mining-land polygons drawn on 2019 Sentinel-2 imagery (pits, dumps, tailings, ponds, plant) | CC BY-SA 4.0 | yes |
| Jasansky et al., ML-ready mining dataset (Zenodo 14195737) | 1,514 S2 tiles, preferred Maus/Tang polygons, a manual mine-type label per tile | see Zenodo record | yes (already local). The GitHub repo `SimonJasansky/mine-segmentation` returned 403 through this sandbox's proxy, so it was not used. |
| USGS MRDS | | public domain | reachable, **not used** (US-centric and stale; it adds little for surface footprints) |
| `manual_mine_type.csv` | mining method and status notes for about 100 well-known mines (Chile/Peru copper, lithium, sanity-check mines) | written from my own knowledge, not checked row by row | in repo |

Because Maus v2 is CC BY-SA, the derived GeoPackage and CSV must be **shared under CC BY-SA 4.0**,
with attribution to ICMM, Maus et al. (2022) and Jasansky et al.

## Method

1. **ICMM.** Keep rows whose `Asset Type` contains "Mine" (8,018 of 8,508; this includes
   Mine;Smelter and similar). Drop one row with an unparseable latitude, leaving 8,017.
   Commodity names are trimmed and lower-cased, and synonyms are merged (thermal/metallurgical
   coal → coal, kept in `coal_type`; chromite → chromium; alumina/aluminium → bauxite;
   ferro-alloys → their metal). The raw primary commodity is kept.
2. **Merge fragments.** Maus polygons closer than 500 m become one footprint ("cluster"). This
   is done in UTM, with an extra pass to join clusters across zone boundaries. Result: 30,212
   clusters.
3. **Match.** A point inside a footprint is matched to it. Otherwise it goes to the nearest
   footprint within 3 km, measured in metres in the point's UTM zone. Points still unmatched
   are tried against the Zenodo preferred polygons, which adds some Tang et al. polygons.
   `match_method` and `match_dist_m` are recorded for every mine.
4. **Shared footprints.** When several ICMM points land on one footprint (a complex such as
   Chuquicamata / Radomiro Tomic / Ministro Hales), every point gets the whole footprint
   (`footprint_km2`), and `shared_footprint=True` is set. The footprint is also split between
   the points: each member polygon goes to its nearest point, and a polygon holding several
   points is cut by their Voronoi cells. This gives `own_footprint_km2` and the `mines_own`
   layer. The split is crude, because pit boundaries are not bisectors.
5. **Quality flags.**
   - `possible_duplicate`: similar names on the same footprint (107 rows).
   - `country_mismatch` / `country_fixed`: `country` takes the Maus polygon's country where
     it disagrees with ICMM. ICMM files about 23 Australian mines under "New Caledonia",
     Pilgangoora and Mount Isa among them.
   - `large_complex`: footprint larger than 100 km² (142 rows).
6. **Mine type.** For `mine_type`, the manual table wins. Next comes the Zenodo tile label
   when a single label overlaps the footprint. Otherwise the value is `unknown` (6,551 rows).

## Outputs

- `mine_inventory.gpkg` (22 MB, full resolution, WGS84). It has three layers:
  - `mines`: one row per ICMM mine. The geometry is the merged footprint, or null when
    unmatched.
  - `mines_own`: the split footprint.
  - `clusters`: 3,893 unique footprints, with the ICMM names on each. Use this layer to avoid
    double counting.

  A copy also sits in the scratch dir `…/scratchpad/mines/out/`.
- `mine_inventory.csv`: the same attributes plus bbox columns and `geometry_wkt_simplified`
  (simplified to 0.0005°, about 50 m).
- `summary_match_rates.csv`, `summary_by_commodity.csv`, `summary_commodity_country.csv`.
  The last one counts matched mines, excluding those labelled underground.
- `summary_chile_peru_copper.csv` lists every Chile/Peru mine with copper among its
  commodities. `summary_chile_peru_copper_openpit.csv` keeps the matched mines labelled open
  pit (26 in Chile, 16 in Peru, from 22 + 16 unique footprints).
- `summary_lithium.csv` covers all 78 ICMM mines that list lithium:

  | deposit type | sites | matched |
  |---|---|---|
  | brine | 17 | 10 |
  | hard rock | 48 | 19 |
  | clay | 1 | 0 |
  | lithium only as a minor commodity | 12 | 10 |

  `summary_zenodo_brine_unnamed.csv` lists 60 Zenodo brine/evaporation-pond footprints that
  have no ICMM name (lithium or potash candidates).
- `summary_sanity_check.csv`: known mines checked against reference coordinates.

## Match rates

Of 8,017 ICMM mines, **4,451 (55.5%) matched**:

| match | mines |
|---|---|
| inside a Maus polygon | 2,562 |
| nearest Maus polygon ≤3 km | 1,854 |
| Zenodo polygon | 35 |
| unmatched | 3,566 |

The match rate depends heavily on the ICMM confidence class: High 85%, Moderate 46%,
Very Low 26%. It also varies by commodity: gold 77%, bauxite 72%, iron ore 61%, copper 60%,
coal 56%, lithium 42%, tin 15%, barium 7%.

Most unmatched points are more than 5 km from any Maus polygon, so a larger search radius
would not help. They fall into four groups:
- underground mines with little surface disturbance;
- mines opened after 2019 (Kathleen Valley, Goulamina, Grota do Cirilo, Manono);
- small or artisanal sites;
- bad ICMM coordinates. One of the two "Los Bronces" rows sits 40 km west of the mine.

## Sanity check (known mines)

Reference points: Escondida, Chuquicamata, Bingham Canyon, Grasberg, Greenbushes,
Cobre Panamá (8.84N, -80.65W), Collahuasi, Cerro Verde, Antamina, Los Pelambres, Toquepala,
Las Bambas, Salar de Atacama and Oyu Tolgoi. Every one of these points falls inside the
footprint matched to the correctly named ICMM record. Caveats:
- **Escondida** shares one 231 km² polygon with Zaldívar.
- **Chuquicamata** shares a 178 km² cluster with RT and MH. It is labelled underground
  (the open pit ended in 2019).
- **Grasberg** is labelled underground (block caves since 2019).
- **Cobre Panamá** is a duplicated ICMM row. Its footprint is only 7.8 km², which looks small
  (2019 imagery, early ramp-up).
- **Salar de Atacama** is one 1,354 km² polygon, far bigger than the evaporation ponds, so it
  is useless for an activity index without clipping.
- **Pilgangoora** failed. ICMM puts it in "New Caledonia", and it matched only a 1.2 km²
  fragment. My reference point (approximate) fell outside every footprint, so check it on
  imagery.

## Caveats

- **A polygon does not prove a mine is active, or even surface-worked.** Maus polygons show
  mining land visible in 2019. That land includes closed pits, tailings and the surface
  plant of underground mines. Most coal matches in China and the US are probably underground
  mines with surface facilities. `mine_type` is `unknown` for 82% of rows. The Zenodo tile
  labels are coarse: they called El Teniente (block cave) "Surface", and the manual table
  overrides that.
- **The footprints date from 2019.** Expansions and new mines since then are missing or
  undersized: Quellaveco, Mina Justa, QB2, Mt Holland, Kathleen Valley.
- **Footprints get merged.** Clustering at 500 m joins neighbouring mines. Escondida joins
  Zaldívar, and Spence, Sierra Gorda and Gregoria form one 286 km² cluster. Antucoya joins
  María Elena (an SQM nitrate operation) in an 858 km² cluster. Huge single polygons also
  exist, such as "Rivera Alta" in Peru at 2,535 km² (artisanal gold region). Use
  `own_footprint_km2` and `large_complex`, and clip to the pit before computing an index.
- **ICMM has errors.** Duplicates (Cobre Panamá, Huaron, Colquiri), wrong countries (New
  Caledonia for Australia), misplaced coordinates and spelling variants ("Collahausi") all
  occur. ICMM coordinates for clustered sites are averages, so they can sit between pits.
- **Lithium coverage in ICMM is thin.** Jiajika, Yichun, Fénix/Hombre Muerto (Livent),
  Clayton Valley projects and most Chinese hard-rock mines are absent.
- **The manual labels are my own, unverified.** Treat them as a starting point.
