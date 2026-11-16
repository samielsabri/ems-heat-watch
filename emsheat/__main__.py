"""
Command line:

  python -m emsheat probe                              # what's in the live NYC dataset
  python -m emsheat fetch  --store store --raw raw     # pull new rows since the watermark
  python -m emsheat ingest --store store FILE_OR_DIR   # reduce a JSON/CSV export into the store
  python -m emsheat analyze --store store --out report [--weather-csv f | --weather noaa]
  python -m emsheat update --store store --out report  # fetch + ingest + analyze (cron this daily)
"""
import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

from . import fetch as F
from . import weather as W
from .ingest import ingest, load_state


def _weather(a, start):
    wx = W.get(a.weather, a.weather_csv, start=start)
    print(f"Weather: {len(wx)} days {wx.index.min().date()} to {wx.index.max().date()} "
          f"({int(wx['forecast'].sum())} forecast)")
    return wx


def _analyze(a):
    from .analyze import run
    from .report import write
    t_first = pd.read_csv(Path(a.store) / "type_daily.csv.gz", usecols=["date"], parse_dates=["date"])["date"].min()
    wx = _weather(a, str((t_first - pd.Timedelta(days=7)).date()))
    ctx = run(a.store, wx, a.out, a.train_end, a.eval_start, a.asof, a.exposure, a.heat_regex,
              a.train_years, a.alpha)
    path = write(ctx, a.out)
    print(f"Report: {path}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="emsheat")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")

    def common(sp):
        sp.add_argument("--store", default="store")

    sp = sub.add_parser("ingest"); common(sp)
    sp.add_argument("input")
    sp.add_argument("--since")
    sp.add_argument("--zip-since", default=None, help="only keep zip-level detail from this date")

    def analyze_args(sp):
        sp.add_argument("--out", default="report")
        sp.add_argument("--weather", default="open-meteo", choices=["open-meteo", "noaa"])
        sp.add_argument("--weather-csv")
        sp.add_argument("--exposure", default="tmax")
        sp.add_argument("--train-end")
        sp.add_argument("--eval-start")
        sp.add_argument("--asof", help="treat this date as today (default: today)")
        sp.add_argument("--heat-regex", default=r"HEAT|ENVIR")
        sp.add_argument("--train-years", type=int, default=3)
        sp.add_argument("--alpha", type=float, default=0.005)

    sp = sub.add_parser("analyze"); common(sp); analyze_args(sp)

    for name in ("fetch", "update"):
        sp = sub.add_parser(name); common(sp)
        sp.add_argument("--raw", default="raw")
        sp.add_argument("--since", help="override the watermark (first run: e.g. 2019-01-01)")
        sp.add_argument("--lookback", type=int, default=3)
        sp.add_argument("--zip-since", default=None)
        if name == "update":
            analyze_args(sp)

    a = p.parse_args(argv)
    if a.cmd == "probe":
        F.probe()
    elif a.cmd == "ingest":
        ingest(a.input, a.store, a.since, a.zip_since)
    elif a.cmd == "analyze":
        _analyze(a)
    else:
        since = pd.Timestamp(a.since) if a.since else F.incremental_since(load_state(a.store), a.lookback)
        raw = Path(a.raw) / since.strftime("%Y%m%d")
        shutil.rmtree(raw, ignore_errors=True)
        print(f"Fetching rows since {since}")
        files = F.fetch_rows(raw, since)
        if files:
            ingest(raw, a.store, zip_since=a.zip_since)
        if a.cmd == "update":
            _analyze(a)


if __name__ == "__main__":
    sys.exit(main())
