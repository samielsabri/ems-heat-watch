"""
Daily temperature for the exposure series.

Sources (no API key needed):
  open-meteo  ERA5-based archive (archive-api.open-meteo.com) for history, plus the
              forecast endpoint for the last week and the next 7 days. Default point is
              Central Park (40.7789, -73.9692).
  noaa        GHCN-Daily station file for Central Park (USW00094728) from NCEI. TMAX only.
  csv         Your own file with columns date, tmax[, tmean, app_tmax] in deg C.

Output: DataFrame indexed by date with tmax (and app_tmax/tmean when available) and a
boolean column 'forecast' marking days that are forecasts, not observations.
"""
import io
import json
import urllib.parse
import urllib.request

import pandas as pd

CENTRAL_PARK = (40.7789, -73.9692)
DAILY = "temperature_2m_max,temperature_2m_mean,apparent_temperature_max"


def _json(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read())


def _om_frame(d):
    df = pd.DataFrame(d["daily"]).rename(columns={
        "time": "date", "temperature_2m_max": "tmax", "temperature_2m_mean": "tmean",
        "apparent_temperature_max": "app_tmax"})
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def open_meteo(start, end=None, lat=CENTRAL_PARK[0], lon=CENTRAL_PARK[1], forecast=True):
    end = pd.Timestamp(end or pd.Timestamp.today()).normalize()
    q = dict(latitude=lat, longitude=lon, daily=DAILY, timezone="America/New_York")
    arch = _om_frame(_json("https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(
        {**q, "start_date": pd.Timestamp(start).date(), "end_date": end.date()})))
    arch["forecast"] = False
    if not forecast:
        return arch.dropna(subset=["tmax"])
    fc = _om_frame(_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {**q, "past_days": 10, "forecast_days": 7})))
    today = pd.Timestamp.today().normalize()
    fc["forecast"] = fc.index >= today
    out = arch.dropna(subset=["tmax"])
    out = pd.concat([out, fc[~fc.index.isin(out.index)]]).sort_index()
    return out


def noaa_central_park(start, end=None):
    url = "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/USW00094728.csv"
    with urllib.request.urlopen(url, timeout=300) as r:
        df = pd.read_csv(io.BytesIO(r.read()), usecols=["DATE", "TMAX"], low_memory=False)
    df["date"] = pd.to_datetime(df["DATE"])
    df["tmax"] = pd.to_numeric(df["TMAX"], errors="coerce") / 10.0
    df = df.set_index("date")[["tmax"]].loc[pd.Timestamp(start):pd.Timestamp(end or "2100-01-01")]
    df["forecast"] = False
    return df.dropna()


def from_csv(path):
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    if "forecast" not in df:
        df["forecast"] = False
    return df


def add_forecast(wx, lat=CENTRAL_PARK[0], lon=CENTRAL_PARK[1]):
    """Append Open-Meteo forecast days (today onward) to an observed series, keeping the observed
    history untouched. Use this so history and forecast share the station exposure definition."""
    q = dict(latitude=lat, longitude=lon, daily=DAILY, timezone="America/New_York", forecast_days=8)
    fc = _om_frame(_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)))
    today = pd.Timestamp.today().normalize()
    fc = fc[fc.index >= today].copy()
    fc["forecast"] = True
    keep = [c for c in wx.columns if c in fc.columns]
    out = pd.concat([wx, fc.loc[~fc.index.isin(wx.index), keep]]).sort_index()
    out["forecast"] = out["forecast"].fillna(False).astype(bool)
    return out


def get(source="open-meteo", path=None, start="2015-01-01", end=None, forecast=False):
    """source: open-meteo (ERA5 grid history + forecast), noaa (Central Park station), or a CSV.
    forecast=True appends Open-Meteo forecast days to a noaa or CSV history."""
    if path:
        wx = from_csv(path)
    elif source == "noaa":
        wx = noaa_central_park(start, end)
    else:
        return open_meteo(start, end)
    return add_forecast(wx) if forecast else wx
