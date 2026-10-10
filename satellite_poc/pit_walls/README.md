# Pit-wall and heap instability: can free radar see it before the company says so?

**Question.** Activity indices catch halts, but halts are announced the same day. Geotechnical
trouble is different. It hurts production for several quarters and often first appears in a
quarterly report. Can free radar see wall or heap movement **before** that disclosure?

**Short answer: not in these four cases.** No free product passed the pre-registered test ahead
of any event. The one good free InSAR product (NASA OPERA DISP-S1) shows a Bingham wall creeping
for years, but nothing that stood out before July 2024. Its 2024 data were also published
14 months after Rio's disclosure.

## 1. What free data could actually be reached (no login, from this sandbox)

| source | what it is | reachable? | notes |
|---|---|---|---|
| Planetary Computer `sentinel-1-rtc` | Sentinel-1 backscatter (amplitude), 10 m | **yes** | Used for the amplitude test. PC has no SLC, coherence or InSAR collection, only `sentinel-1-grd` and `-rtc`. |
| **OPERA DISP-S1** (NASA/JPL), North America | InSAR LOS displacement, 30 m, 12-day | **yes, per point** | The NetCDF granules and zarr stacks need an Earthdata login (HTTP 401). CMR search is open. Browse PNGs are open but only ~90 m colour renders. **ASF's displacement-portal API answers anonymously:** `POST https://d2qmcvu7qty7vn.cloudfront.net/timeseries` with `{"wkt":"POINT(lon lat)","bucket":"asf-cumulus-prod-opera-products","polarization":"VV","flightDirection":"DESCENDING"}` returns the full per-pixel series, with masks. Polygon queries fail server-side (out of memory), so we sampled 656 points. |
| OPERA coverage | | | Bingham: descending frame F26685, Aug 2016-Nov 2025. Ascending F32518 only runs Aug 2016-Jun 2021. **No winter epochs** (Nov-Apr skipped for snow). Not covered: Eagle (Yukon), Canadian Malartic (Quebec), Çöpler (Turkey). |
| OPERA latency | | | The Apr-Jun 2024 Bingham epochs were *produced* on 1 Sep 2025, the Jun 2024-Apr 2025 epochs on 10 Mar 2026. The newest epoch as of Oct 2026 is 7 Nov 2025. **This is a batch archive, not a real-time feed.** |
| **COMET LiCSAR** (Leeds) | Sentinel-1 interferograms + coherence, ~100 m, global frames | **yes** | Recent pairs come from `gws-access.jasmin.ac.uk/public/nceo_geohazards/LiCSAR_products(.public)`, older pairs from `dap.ceda.ac.uk/neodc/comet/data/licsar_products`. GeoTIFF strips allow windowed reads. Çöpler: frames 043A_05026 and 123D_05095, 2014-Sep 2024. Eagle: 079A_02602, Dec 2022-Aug 2025 only. |
| Global S1 coherence (Earth Big Data, AWS) | seasonal coherence, 2019-20 only | yes (anonymous S3) | Not used: one year, no time resolution. |
| ASF HyP3 on-demand InSAR, Sentinel-1 SLC (ASF, Copernicus Data Space) | | **no** | Login needed (Earthdata or Copernicus). |
| EGMS (European Ground Motion Service) | | not tried for download | Needs an EU Login. Covers Europe only (Turkey is not clearly covered), so none of these sites. |
| Umbra open data | X-band spotlight, ~0.3-0.5 m | **yes** | 110 Bingham collects with metadata, Jul 2023-Jan 2025. COG reads, see section 5. |

## 2. Pre-registration (written before any series was computed: `prereg.json`)

- **Reference date D.**
  - Bingham 2024: **16 Jul 2024**, Rio's Q2 operations review, the first disclosure.
  - Bingham Leo: **31 May 2021**, the failure itself; local press reported it 2 Jun 2021.
  - Çöpler: **13 Feb 2024**, failure, disclosed the same day.
  - Eagle: **24 Jun 2024**, failure, disclosed the same day.
- **Segments.** These were drawn from imagery and geometry only.
  - Bingham: six compass sectors, 350-2400 m from the pit bottom (-112.151, 40.523). The 2024 event is scored on the **S** sector (also SW, SE); Leo on **SE** (also S, NE). Control: 3.0-4.5 km ring.
  - Çöpler and Eagle: heap-leach-pad boxes from `../zones.py`. A post-event amplitude map (Çöpler) and the published crown location (Eagle, 64.0418 N, 135.833 W) confirm the failures sit inside them.
- **Baseline.** D-24 months to D-12 months. **Search window:** D-12 months to D-4 weeks.
- **InSAR rule.** The statistic is the segment's 60-day LOS change: median over points or pixels, minus control. A detection needs:
  - |change - baseline mean| > 3 SD, **and** |change| >= 15 mm;
  - three consecutive epochs.
- **Amplitude rule.** The statistic is the share of segment pixels whose VV dB (3x3 boxcar) moved more than 2 dB from the median of the previous 5 passes, minus the same share over control. A detection needs the baseline mean + 3 SD on two consecutive passes.
- **False alarms.** The same rule is re-run with D at every 1 Jan and 1 Jul in the archive, for every segment.
- **Expectation, stated in advance.** Amplitude cannot see cm-scale creep. InSAR only works where coherence survives.

## 3. Results per case (pre-registered)

`results/summary.csv` collects every row: **0 detections out of 20 tests** (method × case × segment).

| case | method | baseline SD | fired before D-4 wk? | comment |
|---|---|---|---|---|
| Bingham 2024 S wall | OPERA desc | 6.5 mm | no | S sector 60-day change stayed inside ±3 SD |
| Bingham 2024 SW / SE | OPERA desc | 3.6 / 6.8 mm | no | |
| Bingham Leo 2021 SE | OPERA desc / asc | 5.3 / 6.0 mm | no | Ascending had only 2 spring epochs before the failure |
| Bingham both | S1 amplitude | 5 pts | no | Spikes are winter snow. S sector fires in 1 of 11 pseudo-date windows |
| Çöpler heap | LiCSAR asc / desc | 38.8* / 5.4 mm | no | 60-day change within -14…+10 mm (asc) and -9…+4 mm (desc) all year |
| Çöpler heap | S1 amplitude | 8 pts | no | The slide itself only reached 16 against a 22-point threshold |
| Eagle heap | LiCSAR asc | n/a | **not testable** | LiCSAR starts Dec 2022, so the baseline has 6 points |
| Eagle heap | S1 amplitude | 6 pts | no | |

\*Inflated by a −77 mm single-pair jump in Jun 2022, almost certainly an unwrapping error. With a
clean baseline the result is the same, because no 60-day change in the window reached the 15 mm floor.

The InSAR rule never fired in any pseudo-date window at Bingham (0 of 84 descending and 0 of 30
ascending sector-windows) and fired once at Çöpler (1 of 20, in the unwrapping-error period). It is conservative: it does not cry wolf, and it also saw nothing.

Figures:
- `figures/bingham_opera_overview_des.png`
- `figures/bingham_opera_2024_des.png`
- `figures/bingham_opera_2021_{asc,des}.png`
- `figures/copler_licsar.png`, `figures/eagle_licsar.png`
- `figures/*_amplitude.png`

## 4. What the data do show (exploratory, after the test; treat as hypotheses)

- **Bingham walls creep, steadily.** OPERA descending, LOS rates vs the control ring:

  | sector | 2016-May 2021 | Jun 2021-Jul 2024 | after Jul 2024 |
  |---|---|---|---|
  | SE wall | −26 mm/yr | −42 mm/yr | −21 mm/yr |
  | S wall | −3.4 mm/yr | −7.9 mm/yr | −12 mm/yr |

  The S wall did speed up over the years, but only gradually. Year-on-year (Sep-Sep), its
  change was −29 mm (2021-22), +21 mm (2022-23) and −9 mm (2023-24): no clean ramp before
  the disclosure.
- **Bingham spring 2024 (Apr 10 → Jul 3).**
  - A cluster on the lower S wall dropped by 20-40 mm (`figures/bingham_opera_map_spring.png`). The S-sector median was −11 mm, against −3, −9 and −2 mm in 2021-23 and −18 mm in 2025.
  - The points rebound later each summer, and every year shows the same post-winter drop. So part of this is seasonal: snowmelt, or elevation-correlated troposphere in a 1 km deep pit.
  - The hotspot share (points down >20 mm in 60 days, `figures/bingham_opera_hotspots_des.png`) peaked at 0.34 in Jun 2024. Earlier years reached 0.33-0.57, always as single-epoch spikes.
  - **Even if this were the movement Rio monitored in Q2, it is no lead.** The epochs are April-June, right before the 16 July disclosure, and the data were published in Sep 2025.
- **Bingham autumn 2023.** A band along the upper S rim lost about 13 mm from Aug to Oct 2023. That is the largest of five years for that window (`figures/bingham_opera_map_autumn.png`), but it is small and similar to the 2021-22 SE-wall patches. It would not have stood out in advance.
- **Leo (31 May 2021, 19 Mt).** No acceleration on the SE sector in Apr-May 2021, only the long-running creep. Kennecott predicted the failure with ground radar. Fast pre-failure movement (cm/day) aliases or decorrelates C-band 12-day InSAR, and OPERA masks those pixels.
- **Çöpler.** A vendor analysis (Descartes Labs, 10 m custom InSAR) reports about 80 mm of ascending motion on the heap's SW corner from Sep 2023. LiCSAR at 100 m does not reproduce it: the heap-wide median moved −13 mm (asc) and −5 mm (desc) from Feb 2023 to Feb 2024. Much of the heap is incoherent in LiCSAR pairs (`figures/copler_licsar_map_*.png`), and a corner signal is diluted at 100 m.
- **Eagle.** The two coherent pairs in the five weeks before the failure (15-27 May and 8-20 Jun 2024) each moved +7 to +9 mm towards the satellite. Most of 2023 stayed within ±5 mm, but Jan-Apr 2023 also rose about 9 mm. With snowmelt and only two pairs, this is suggestive at best, and it falls inside the 4-week exclusion.

## 5. Umbra (sub-metre SAR), visual check

`umbra_walls.py` picks collects with matching geometry (ascending, left-looking, azimuth 75-125°,
incidence 25-51°) and reads only the south-half window from the COGs
(`figures/bingham_umbra_south_wall.png`).

- Benches and haul roads are crisp.
- GEC products are ellipsoid-geocoded, not terrain-corrected. In a 1.2 km deep pit, layover changes completely with incidence (50° in 2023, 30° in 2024), so only the Mar-Oct 2024 chips compare like with like.
- No scarp or slump stands out by eye.
- A real test would need co-registered SICD stacks with matching geometry (coherent change detection), which Umbra's ad-hoc tasking rarely provides. Equipment counting is left to the other agent.

## 6. Caveats

- Only four events, all at different sites. The events where the company is slow to disclose (Bingham 2024) are rare and have fuzzy onset dates. "Highwall movement monitored during Q2" gives no start date.
- **OPERA's snow gap** (Nov-Apr) blanks exactly the months before a spring onset.
- Sector medians dilute a fault-bounded movement a few hundred metres wide. The hotspot view helps, but it was not pre-registered.
- C-band InSAR sees about mm/day at most before aliasing. Accelerating walls, the ones that matter, drop out as "masked" pixels.
- Active benches and fresh heap lifts decorrelate. A pit wall that is being mined is the hardest surface for InSAR.
- **Latency.** OPERA came 14+ months after the fact. LiCSAR frames update irregularly: 043A stopped in Oct 2024.

## 7. Could this ever give a lead over disclosure?

**Plausibly yes in principle. With what is free and anonymous, not reliably.**

- **Bingham shows the physics is visible.** Walls creep at 10-40 mm/yr, and OPERA measures that. But turning it into a lead needs three things:
  - near-real-time InSAR from your own Sentinel-1 SLC processing (a free Earthdata login plus compute), not the batch archive;
  - point-scale anomaly detection on fault-bounded wall blocks, not sector medians;
  - a validation set many times larger than four events.
- **Where the wall is being mined, InSAR loses coherence; where it is accelerating, the phase aliases.** That is exactly when the company already knows from its own ground radar.
- A more realistic free signal is slow, multi-year acceleration of a non-mined wall (like the S wall's −3 → −8 → −12 mm/yr). It would be a slow risk flag, not a dated trade trigger.

## Scripts

| script | does |
|---|---|
| `prereg.json` | pre-registered dates, segments, rules (read by every script) |
| `basemap.py` | Sentinel-2 chip with lon/lat graticule and segment outlines (segments drawn from imagery) |
| `opera_disp.py SITE OUT.csv` | anonymous OPERA DISP-S1 point series from the ASF displacement API, on a sector grid |
| `opera_analyze.py LONG.csv results figures` | segment series, pre-registered test, false-alarm scan, figures |
| `opera_map.py` / `opera_hotspot.py` | exploratory point maps / hotspot shares (not pre-registered) |
| `licsar_ts.py SITE FRAME START END OUT.csv` | LiCSAR 12-day interferogram chain: segment minus control LOS increments |
| `licsar_analyze.py SITE PREFIX FIG TRACK=CSV…` | pre-registered test on LiCSAR series |
| `licsar_map.py` | exploratory summed-increment maps |
| `amplitude.py SITE STACK.npz PREFIX FIG` | Sentinel-1 RTC amplitude change index + pre-registered test |
| `umbra_walls.py` | Umbra COG wall chips for one viewing geometry |
| `detect.py`, `style.py` | shared rule and plot style |
| `summarize.py results` | `results/summary.csv` |

Reproduce (big files go to a scratch dir `$S`; options go before `--`):

```bash
python ../s1stack.py --bbox -112.19,40.49,-112.11,40.56 2019-01-01/2026-10-01 $S/bingham_s1.npz
python opera_disp.py bingham $S/bingham_opera_long.csv --cache $S/opera_cache   # also in results/bingham_opera_points.csv.gz
python opera_analyze.py $S/bingham_opera_long.csv results figures
python basemap.py --step 0.01 -- -112.19,40.49,-112.11,40.56 2023-06-01/2023-10-01 $S/bingham_s2b.png
python opera_map.py $S/bingham_opera_long.csv $S/bingham_s2b.png -112.19,40.49,-112.11,40.56 figures/bingham_opera_map_spring.png DESCENDING 0401 0710 2021 2022 2023 2024 2025
python opera_hotspot.py $S/bingham_opera_long.csv results/bingham_opera_hotspots_des.csv figures/bingham_opera_hotspots_des.png
python licsar_ts.py copler 043A_05026_131313 2017-01-01 2024-06-01 $S/copler_asc.csv --save-maps $S/copler_asc.npz
python licsar_ts.py copler 123D_05095_141313 2017-01-01 2024-06-01 $S/copler_desc.csv --save-maps $S/copler_desc.npz
python licsar_ts.py eagle 079A_02602_131313 2022-06-01 2024-08-01 $S/eagle_asc.csv --save-maps $S/eagle_asc.npz
python licsar_analyze.py copler results/copler_licsar figures/copler_licsar.png asc043=$S/copler_asc.csv desc123=$S/copler_desc.csv
python licsar_analyze.py eagle results/eagle_licsar figures/eagle_licsar.png asc079=$S/eagle_asc.csv
python licsar_map.py $S/copler_asc.npz copler figures/copler_licsar_map_asc.png 0901 0210 2021 2022 2023 2024
python amplitude.py bingham $S/bingham_s1.npz results/bingham figures/bingham_amplitude.png   # same for copler, eagle stacks
python umbra_walls.py --dates 2023-08-30,2023-10-02,2023-11-14,2024-01-09,2024-03-11,2024-04-28,2024-06-12,2024-08-02,2024-10-31 --az 100 --aztol 25 --inc 38 --inctol 13 --res 2.5 -- results/bingham_umbra_index.csv -112.180,40.497,-112.125,40.530 figures/bingham_umbra_south_wall.png
python summarize.py results
```

Sources for event dates:
- Rio Tinto Q2 2024 operations review, 16 Jul 2024 ([SEC 6-K](https://www.sec.gov/Archives/edgar/data/863064/000162828024031937/ex1_2qresults16jul24.htm)), and Q3 review, 16 Oct 2024 ([SEC 6-K](https://www.sec.gov/Archives/edgar/data/863064/000162828024042902/ex01_2024-3qor.htm))
- Leo failure: [Peik et al., SSIM 2025](https://papers.acg.uwa.edu.au/d/2535_32_Peik/32_Peik.pdf); [S&P Global, 4 Jun 2021](https://www.spglobal.com/commodity-insights/en/news-research/latest-news/metals/060421-rio-tinto-utah-copper-processing-not-impacted-by-landslip)
- Çöpler: [SSR Mining](https://ssrmining.com/2024-copler-incident/); [Descartes Labs retrospective](https://earthdaily.com/blog/çöpler-mine-disaster-a-retroactive-analysis-to-safeguard-mine-sites)
- Eagle: [Landslide Blog](https://eos.org/thelandslideblog/eagle-gold-mine)
