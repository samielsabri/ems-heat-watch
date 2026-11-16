"""
Stream NYC EMS Incident Dispatch records into compact daily aggregates.

Accepts any of the formats NYC Open Data serves for dataset 76xm-jjuj:
  - JSON array of row objects (v3 query.json, SODA /resource/76xm-jjuj.json, or pages from fetch.py)
  - CSV export (any header case/spacing; ISO or MM/DD/YYYY hh:mm:ss AM datetimes)
  - either of the above gzipped, or a directory of such files

The full dataset is tens of millions of rows, so nothing is loaded whole: rows are
streamed in chunks and reduced to two tables.

  type_daily  date x borough x field(final|initial) x call_type
              -> n, hi (severity 1-3), transport, resp_sum, resp_n
  zip_daily   date x zipcode x final_call_type -> n, hi   (only from --zip-since on)

Incremental updates replace whole dates: every date present in the new batch is
dropped from the store and re-added from the batch. fetch.py therefore always
re-pulls whole days (with a lookback for late final_call_type edits).
"""
import gzip
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

KEEP = [
    "incident_id", "incident_datetime", "initial_call_type", "final_call_type",
    "initial_severity_level_code", "borough", "zipcode",
    "incident_response_seconds_qy", "valid_incident_rspns_time_indc", "first_to_hosp_datetime",
]
ALIASES = {"cad_incident_id": "incident_id"}
TYPE_KEYS = ["date", "borough", "field", "call_type"]
ZIP_KEYS = ["date", "zipcode", "call_type"]


def norm(col):
    c = re.sub(r"[^0-9a-z]+", "_", str(col).strip().lower()).strip("_")
    return ALIASES.get(c, c)


def _files(path):
    p = Path(path)
    if p.is_dir():
        return sorted(f for f in p.iterdir() if re.search(r"\.(json|csv)(\.gz)?$", f.name, re.I))
    return [p]


def _kind(p):
    name = p.name.lower().removesuffix(".gz")
    if name.endswith(".json"):
        return "json"
    if name.endswith(".csv"):
        return "csv"
    raise ValueError(f"Unrecognised file type: {p}")


def iter_chunks(path, chunksize=250_000):
    """Yield DataFrames of raw rows (string columns, normalised names)."""
    for f in _files(path):
        if _kind(f) == "csv":
            for df in pd.read_csv(f, dtype=str, chunksize=chunksize, keep_default_na=False):
                df.columns = [norm(c) for c in df.columns]
                yield df[[c for c in KEEP if c in df.columns]]
        else:
            import ijson
            opener = gzip.open if f.name.lower().endswith(".gz") else open
            with opener(f, "rb") as fh:
                buf = []
                for row in ijson.items(fh, "item", use_float=True):
                    buf.append({norm(k): v for k, v in row.items() if norm(k) in KEEP})
                    if len(buf) >= chunksize:
                        yield pd.DataFrame(buf)
                        buf = []
                if buf:
                    yield pd.DataFrame(buf)


def parse_dt(s):
    s = s.astype(str)
    d = pd.to_datetime(s, format="ISO8601", errors="coerce")
    miss = d.isna()
    if miss.any():
        d[miss] = pd.to_datetime(s[miss], format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    return d


def _clean_str(s):
    return s.fillna("").astype(str).str.strip().str.upper().replace("", "UNKNOWN")


def reduce_chunk(df, since=None, zip_since=None):
    """Raw rows -> (type_daily, zip_daily, max_datetime, n_rows)."""
    for c in KEEP:
        if c not in df.columns:
            df[c] = None
    dt = parse_dt(df["incident_datetime"])
    ok = dt.notna()
    if since is not None:
        ok &= dt >= pd.Timestamp(since)
    df, dt = df[ok], dt[ok]
    if df.empty:
        return None, None, None, 0

    sev = pd.to_numeric(df["initial_severity_level_code"], errors="coerce")
    resp = pd.to_numeric(df["incident_response_seconds_qy"], errors="coerce")
    valid = df["valid_incident_rspns_time_indc"].fillna("").astype(str).str.upper().eq("Y")
    resp = resp.where(valid & resp.between(0, 6 * 3600))
    hosp = df["first_to_hosp_datetime"].fillna("").astype(str).str.strip()

    base = pd.DataFrame({
        "date": dt.dt.normalize().values,
        "borough": _clean_str(df["borough"]).values,
        "zipcode": df["zipcode"].fillna("").astype(str).str.extract(r"(\d{5})", expand=False).fillna("UNKNOWN").values,
        "final": _clean_str(df["final_call_type"]).values,
        "initial": _clean_str(df["initial_call_type"]).values,
        "n": 1,
        "hi": (sev <= 3).astype(int).values,              # FDNY segments 1-3 = life-threatening
        "transport": (hosp != "").astype(int).values,
        "resp_sum": resp.fillna(0).values,
        "resp_n": resp.notna().astype(int).values,
    })
    final_missing = base["final"].eq("UNKNOWN")
    base.loc[final_missing, "final"] = base.loc[final_missing, "initial"]

    vals = ["n", "hi", "transport", "resp_sum", "resp_n"]
    parts = []
    for field in ("final", "initial"):
        g = base.groupby(["date", "borough", field], sort=False)[vals].sum().reset_index()
        parts.append(g.rename(columns={field: "call_type"}).assign(field=field))
    tdaily = pd.concat(parts, ignore_index=True)[TYPE_KEYS + vals]

    zdaily = None
    zb = base if zip_since is None else base[base["date"] >= pd.Timestamp(zip_since)]
    if not zb.empty:
        zdaily = (zb.groupby(["date", "zipcode", "final"], sort=False)[["n", "hi"]].sum()
                  .reset_index().rename(columns={"final": "call_type"}))
    return tdaily, zdaily, dt.max(), len(df)


def _collapse(frames, keys):
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True).groupby(keys, sort=True).sum().reset_index()


def ingest(path, store, since=None, zip_since=None, chunksize=250_000, log=print):
    """Reduce a raw export into the store. Dates in the batch replace stored dates."""
    store = Path(store)
    store.mkdir(parents=True, exist_ok=True)
    tparts, zparts, wm, total = [], [], None, 0
    for i, chunk in enumerate(iter_chunks(path, chunksize)):
        t, z, mx, n = reduce_chunk(chunk, since, zip_since)
        total += n
        if n:
            tparts.append(t)
            zparts.append(z)
            wm = mx if wm is None else max(wm, mx)
        # keep memory bounded on huge files
        if len(tparts) >= 8:
            tparts = [_collapse(tparts, TYPE_KEYS)]
            zparts = [_collapse(zparts, ZIP_KEYS)]
        log(f"  chunk {i + 1}: {total:,} rows")
    if total == 0:
        log("No rows ingested.")
        return None
    tnew, znew = _collapse(tparts, TYPE_KEYS), _collapse(zparts, ZIP_KEYS)

    state = load_state(store)
    batch_dates = set(tnew["date"].unique())
    for name, new, keys in (("type_daily", tnew, TYPE_KEYS), ("zip_daily", znew, ZIP_KEYS)):
        f = store / f"{name}.csv.gz"
        if f.exists():
            old = pd.read_csv(f, parse_dates=["date"], dtype={"zipcode": str})
            old = old[~old["date"].isin(batch_dates)]
            new = old if new is None else pd.concat([old, new], ignore_index=True)
        if new is not None:
            new.sort_values(keys).to_csv(f, index=False, compression="gzip")

    prev_wm = pd.Timestamp(state["watermark"]) if state.get("watermark") else None
    state["watermark"] = str(max(wm, prev_wm) if prev_wm is not None else wm)
    state["rows_ingested"] = state.get("rows_ingested", 0) + total
    state.setdefault("batches", []).append({
        "source": str(path), "rows": total,
        "first_date": str(min(batch_dates).date()), "last_date": str(max(batch_dates).date()),
        "ingested_at": pd.Timestamp.now().isoformat(timespec="seconds"),
    })
    (store / "state.json").write_text(json.dumps(state, indent=2))
    log(f"Ingested {total:,} rows covering {min(batch_dates).date()} to {max(batch_dates).date()}; "
        f"watermark {state['watermark']}")
    return state


def load_state(store):
    f = Path(store) / "state.json"
    return json.loads(f.read_text()) if f.exists() else {}


def load_store(store):
    store = Path(store)
    t = pd.read_csv(store / "type_daily.csv.gz", parse_dates=["date"])
    zf = store / "zip_daily.csv.gz"
    z = pd.read_csv(zf, parse_dates=["date"], dtype={"zipcode": str}) if zf.exists() else None
    return t, z, load_state(store)


def last_complete_day(state, t):
    """The watermark day is partial unless the last record is late in the evening."""
    wm = pd.Timestamp(state["watermark"]) if state.get("watermark") else t["date"].max()
    last = wm.normalize()
    return last if wm.hour >= 23 else last - pd.Timedelta(days=1)
