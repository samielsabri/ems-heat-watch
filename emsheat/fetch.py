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


# --------------------------------------------------------------------------- #
# Server-side aggregation (SoQL $group). Produces the store tables directly,
# month by month, without downloading rows. ~6 s per month per table.
# --------------------------------------------------------------------------- #
_VALID_RESP = ("valid_incident_rspns_time_indc='Y' and "
               "incident_response_seconds_qy between 0 and 21600")
_TYPE_SELECT = (
    "date_trunc_ymd(incident_datetime) as date, borough, {f}_call_type as call_type, count(*) as n, "
    "sum(case(initial_severity_level_code in ('1','2','3'),1,true,0)) as hi, "
    "sum(case(first_to_hosp_datetime IS NOT NULL,1,true,0)) as transport, "
    f"sum(case({_VALID_RESP}, incident_response_seconds_qy, true, 0)) as resp_sum, "
    f"sum(case({_VALID_RESP},1,true,0)) as resp_n")
_ZIP_SELECT = ("date_trunc_ymd(incident_datetime) as date, zipcode, final_call_type as call_type, "
               "count(*) as n, sum(case(initial_severity_level_code in ('1','2','3'),1,true,0)) as hi")


def _grouped(select, group, where, page=50_000):
    rows, offset = [], 0
    while True:
        r = _get({"$select": select, "$where": where, "$group": group,
                  "$order": group, "$limit": page, "$offset": offset})
        rows += r
        if len(r) < page:
            return rows
        offset += page


def daily_counts(since, until=None):
    """Server-side total rows per day: the reference for checking a local row download."""
    where = f"incident_datetime >= '{pd.Timestamp(since):%Y-%m-%dT%H:%M:%S}'"
    if until:
        where += f" AND incident_datetime < '{pd.Timestamp(until):%Y-%m-%dT%H:%M:%S}'"
    r = _grouped("date_trunc_ymd(incident_datetime) as date, count(*) as n", "date", where)
    s = pd.DataFrame(r)
    return pd.Series(s["n"].astype(int).values, index=pd.to_datetime(s["date"]), name="n").sort_index()


def fetch_aggregates(cache_dir, since, until=None, zip_since=None, log=print):
    """
    One cached CSV per month and table in cache_dir (resumable: finished months are
    skipped, except the last two, which are always re-pulled for late edits).
    Returns (type_daily, zip_daily, watermark) in the ingest.py store schema.
    """
    from .ingest import TYPE_KEYS, ZIP_KEYS
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    until = pd.Timestamp(until) if until else pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    months = pd.date_range(pd.Timestamp(since).replace(day=1), until - pd.Timedelta(days=1), freq="MS")
    recent = set(months[-2:])
    tparts, zparts = [], []
    for m in months:
        lo, hi = max(m, pd.Timestamp(since)), min(m + pd.offsets.MonthBegin(1), until)
        where = f"incident_datetime >= '{lo:%Y-%m-%dT%H:%M:%S}' AND incident_datetime < '{hi:%Y-%m-%dT%H:%M:%S}'"
        jobs = [(f"type_final_{m:%Y%m}", _TYPE_SELECT.format(f="final"), "date, borough, call_type", "final"),
                (f"type_initial_{m:%Y%m}", _TYPE_SELECT.format(f="initial"), "date, borough, call_type", "initial")]
        if zip_since is not None and hi > pd.Timestamp(zip_since):
            zl = max(lo, pd.Timestamp(zip_since))
            zw = f"incident_datetime >= '{zl:%Y-%m-%dT%H:%M:%S}' AND incident_datetime < '{hi:%Y-%m-%dT%H:%M:%S}'"
            jobs.append((f"zip_{m:%Y%m}", _ZIP_SELECT, "date, zipcode, call_type", None, zw))
        for job in jobs:
            name, select, group, field = job[:4]
            w = job[4] if len(job) > 4 else where
            f = cache / f"{name}.csv.gz"
            if f.exists() and m not in recent:
                df = pd.read_csv(f, dtype={"zipcode": str, "call_type": str, "borough": str},
                                 keep_default_na=False)
            else:
                df = pd.DataFrame(_grouped(select, group, w))
                df.to_csv(f, index=False, compression="gzip")
                log(f"  {name}: {len(df):,} groups, {pd.to_numeric(df.get('n', pd.Series(dtype=int))).sum():,} calls")
            if df.empty:
                continue
            df["date"] = pd.to_datetime(df["date"]).dt.normalize()
            for c in ("n", "hi", "transport", "resp_sum", "resp_n"):
                if c in df:
                    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
            df["call_type"] = df["call_type"].fillna("").astype(str).str.strip().str.upper().replace("", "UNKNOWN")
            if field:
                df["borough"] = df["borough"].fillna("").astype(str).str.strip().str.upper().replace("", "UNKNOWN")
                tparts.append(df.assign(field=field))
            else:
                df["zipcode"] = df["zipcode"].fillna("").astype(str).str.extract(r"(\d{5})", expand=False).fillna("UNKNOWN")
                zparts.append(df)
    t = pd.concat(tparts, ignore_index=True).groupby(TYPE_KEYS, sort=True).sum(numeric_only=True).reset_index()
    z = (pd.concat(zparts, ignore_index=True).groupby(ZIP_KEYS, sort=True).sum(numeric_only=True).reset_index()
         if zparts else None)
    wm = _get({"$select": "max(incident_datetime) as latest"})[0]["latest"]
    return t, z, pd.Timestamp(wm)
