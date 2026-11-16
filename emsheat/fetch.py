"""
Pull EMS dispatch rows from NYC Open Data (Socrata SODA API), incrementally.

Untested against the live API from the build environment (network blocked there);
the query shapes follow the standard SODA 2.x conventions.

  - Full rows, paged, ordered by incident_datetime, from a start datetime.
  - Incremental mode starts from the store watermark minus a lookback (default 3
    days) and floors to midnight, so whole days are re-pulled and late edits to
    final_call_type are picked up. ingest.py replaces those dates.
  - Optional: SOCRATA_APP_TOKEN env var raises rate limits (free at data.cityofnewyork.us).
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://data.cityofnewyork.us/resource/76xm-jjuj.json"


def _get(params, retries=4):
    url = BASE + "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json"}
    if os.environ.get("SOCRATA_APP_TOKEN"):
        headers["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            wait = 5 * 2 ** attempt
            print(f"  retry in {wait}s ({e})")
            time.sleep(wait)


def fetch_rows(out_dir, since, until=None, page=50_000, log=print):
    """Write pages of raw rows as JSON arrays to out_dir. Returns list of files."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    since = pd.Timestamp(since).strftime("%Y-%m-%dT%H:%M:%S")
    where = f"incident_datetime >= '{since}'"
    if until:
        where += f" AND incident_datetime < '{pd.Timestamp(until).strftime('%Y-%m-%dT%H:%M:%S')}'"
    files, offset = [], 0
    while True:
        rows = _get({"$where": where, "$order": "incident_datetime, incident_id",
                     "$limit": page, "$offset": offset})
        if not rows:
            break
        f = out / f"page_{offset // page:05d}.json"
        f.write_text(json.dumps(rows))
        files.append(f)
        offset += len(rows)
        log(f"  {offset:,} rows (last {rows[-1].get('incident_datetime')})")
        if len(rows) < page:
            break
    return files


def incremental_since(state, lookback_days=3, default="2019-01-01"):
    wm = state.get("watermark")
    if not wm:
        return pd.Timestamp(default)
    return (pd.Timestamp(wm) - pd.Timedelta(days=lookback_days)).normalize()


def probe(log=print):
    """Quick look at what the live dataset contains: latest record and call types."""
    latest = _get({"$select": "max(incident_datetime) as latest"})
    types = _get({"$select": "final_call_type, count(*) as n", "$group": "final_call_type",
                  "$order": "n desc", "$limit": 500})
    log(f"Latest incident_datetime: {latest[0].get('latest')}")
    log(f"{len(types)} final call types; top 40:")
    for t in types[:40]:
        log(f"  {t.get('final_call_type', ''):10s} {int(t['n']):>12,}")
    return latest, types
