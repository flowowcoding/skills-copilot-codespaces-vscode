#!/usr/bin/env python3
"""Write data/signal/MANIFEST.json: dataset version, build time, row counts and sha256 of every
signal / feature / benchmark file, so a later reader can check which vintage of the point-in-time
signal they hold.  Usage: python build_manifest.py [--version bsw-signal-v1.0]"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="bsw-signal-v1.0")
    a = ap.parse_args()
    files = {}
    for f in sorted(glob.glob(os.path.join(D, "*", "*.csv")) + glob.glob(os.path.join(D, "*", "*.csv.gz"))):
        b = open(f, "rb").read()
        rows = None if f.endswith(".gz") else b.count(b"\n") - 1
        files[os.path.relpath(f, D)] = dict(sha256=hashlib.sha256(b).hexdigest(), bytes=len(b), rows=rows)
    scripts = {os.path.basename(f): hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
               for f in sorted(glob.glob(os.path.join(HERE, "*.py")))}
    man = dict(version=a.version, built_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               primary_signal="signal/bsw_signal_v1.csv (pre-registered spec, model_version bsw_sat_v1_v1)",
               preregistered="2026-10-11 04:25 UTC (README)", files=files, scripts_sha256_16=scripts)
    json.dump(man, open(os.path.join(D, "signal", "MANIFEST.json"), "w"), indent=1)
    print(len(files), "files")


if __name__ == "__main__":
    main()
