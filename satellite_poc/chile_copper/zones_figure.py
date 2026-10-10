"""Draw every stack's pit polygons on a recent Sentinel-2 chip and tile them into one figure.

Usage:
    python zones_figure.py WORK_DIR OUT.png [--dates 2025-11-01/2026-03-31]

Calls chip.py once per stack in mines.json (chips saved in WORK_DIR), then builds a 3-row
montage with the stack name in the corner of each tile.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("work"); ap.add_argument("out"); ap.add_argument("--dates", default="2025-11-01/2026-03-31")
a = ap.parse_args()
here = Path(__file__).parent
cfg = json.load(open(here / "mines.json"))
tiles, H = [], 520
for st, bbox in cfg["stacks"].items():
    mines = ",".join(k for k, v in cfg["mines"].items() if v["stack"] == st)
    png = Path(a.work) / f"v_{st}.png"
    if not png.exists():
        subprocess.run([sys.executable, str(here / "chip.py"), "--zones", str(here / "mines.json"), "--mine", mines,
                        "--step", "0.01", "--", ",".join(map(str, bbox)), a.dates, str(png)], check=True)
    im = Image.open(png)
    im = im.resize((int(im.width * H / im.height), H))
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 22, len(st) * 8 + 10, H], fill=(0, 0, 0))
    d.text((4, H - 18), st, fill=(255, 255, 255))
    tiles.append(im)
n = -(-len(tiles) // 3)
rows = [tiles[i:i + n] for i in range(0, len(tiles), n)]
W = max(sum(t.width for t in r) for r in rows)
M = Image.new("RGB", (W, H * len(rows)), (252, 252, 251))
for i, r in enumerate(rows):
    x = 0
    for t in r:
        M.paste(t, (x, i * H)); x += t.width
M.save(a.out)
print(a.out, M.size)
