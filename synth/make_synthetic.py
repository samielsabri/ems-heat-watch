"""
Synthetic test data in the exact schema of NYC EMS Incident Dispatch Data (76xm-jjuj).

Purpose: exercise the pipeline end to end and check it recovers known effects. Nothing
here is real. Call-type codes follow the style of the real dataset; 'HEAT' is a
placeholder for whatever heat/environmental code the real data uses (confirm with
`python -m emsheat probe`).

Ground truth written to data/synthetic/truth.json:
  - per-type cumulative log-RR per degC above 27 C
  - zips with doubled heat sensitivity
  - injected heat waves

"Today" in this world is 2025-07-21: records run to 03:00 that morning, weather has
observations to 2025-07-20 and a 7-day forecast with another heat wave.
"""
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(20250721)
OUT = Path(__file__).resolve().parent.parent / "data" / "synthetic"
OUT.mkdir(parents=True, exist_ok=True)

START, END = pd.Timestamp("2021-01-01"), pd.Timestamp("2025-07-21")
WX_END = pd.Timestamp("2025-07-27")
TODAY = pd.Timestamp("2025-07-21")
T_REF = 27.0
TOTAL_PER_DAY = 420

# type: (share, heat logRR per degC above 27, winter amplitude, severity mean)
TYPES = {
    "SICK":   (0.180, 0.030, 0.05, 5),
    "INJURY": (0.140, 0.000, -0.08, 5),
    "DIFFBR": (0.095, 0.020, 0.20, 3),
    "EDP":    (0.080, 0.000, -0.05, 6),
    "UNC":    (0.060, 0.045, 0.05, 2),
    "CARD":   (0.050, 0.010, 0.10, 2),
    "ABDPN":  (0.050, 0.000, 0.00, 5),
    "DRUG":   (0.050, 0.020, -0.05, 4),
    "OTHER":  (0.060, 0.000, 0.00, 6),
    "RESPIR": (0.040, 0.000, 0.35, 4),
    "CVAC":   (0.030, 0.000, 0.05, 2),
    "OBMIS":  (0.020, 0.000, 0.00, 4),
    "SEIZ":   (0.030, 0.000, 0.00, 3),
    "ARREST": (0.012, 0.015, 0.10, 1),
    "HEAT":   (0.0015, 0.20, -1.50, 4),
}
NAMES = list(TYPES)
share = np.array([TYPES[t][0] for t in NAMES])
share = share / share.sum()
beta = np.array([TYPES[t][1] for t in NAMES])
wamp = np.array([TYPES[t][2] for t in NAMES])

# ---------------- weather ----------------
days = pd.date_range(START - pd.Timedelta(days=5), WX_END)
doy = days.dayofyear.values
clim = 16.8 + 12.6 * np.cos(2 * np.pi * (doy - 200) / 365.25)
noise = np.zeros(len(days))
for i in range(1, len(days)):
    noise[i] = 0.70 * noise[i - 1] + rng.normal(0, 2.2)
tmax = clim + noise
waves = []
for yr in range(2021, 2026):
    starts = {2024: ["2024-06-18", "2024-07-08", "2024-08-27"],
              2025: ["2025-06-22", "2025-07-22"]}.get(yr)
    if starts is None:
        starts = [str(pd.Timestamp(f"{yr}-06-15") + pd.Timedelta(days=int(d))) [:10]
                  for d in sorted(rng.choice(np.arange(0, 80), 3, replace=False))]
    for s in starts:
        L = int(rng.integers(3, 7))
        bump = rng.uniform(4.5, 6.5)
        idx = np.where((days >= pd.Timestamp(s)) & (days < pd.Timestamp(s) + pd.Timedelta(days=L)))[0]
        shape = np.sin(np.linspace(0.35, np.pi - 0.35, len(idx)))
        tmax[idx] += bump * shape + 1.0
        waves.append(dict(start=s, days=L))
tmax = np.round(tmax, 1)
wx = pd.DataFrame({"date": days, "tmax": tmax})
wx["forecast"] = wx["date"] >= TODAY
wx.to_csv(OUT / "weather_synthetic.csv", index=False)
temp = pd.Series(tmax, index=days)

# ---------------- zips ----------------
zips = ([("MANHATTAN", f"{z:05d}") for z in range(10001, 10041)] +
        [("BRONX", f"{z:05d}") for z in range(10451, 10476)] +
        [("BROOKLYN", f"{z:05d}") for z in range(11201, 11240)] +
        [("QUEENS", f"{z:05d}") for z in list(range(11354, 11375)) + list(range(11411, 11430))] +
        [("RICHMOND / STATEN ISLAND", f"{z:05d}") for z in range(10301, 10315)])
zboro = np.array([b for b, _ in zips])
zcode = np.array([z for _, z in zips])
zw = rng.lognormal(0, 0.45, len(zips))
zw = zw / zw.sum()
vuln_list = [f"{z}" for z in range(10451, 10461)] + ["11207", "11208", "11212", "11233", "10029", "10035"]
zv = np.where(np.isin(zcode, vuln_list), 1.5, 1.0)

# ---------------- daily rates ----------------
ems_days = pd.date_range(START, END)
nd = len(ems_days)
pos = (temp - T_REF).clip(lower=0)
H = (0.6 * pos + 0.3 * pos.shift(1) + 0.1 * pos.shift(2)).reindex(ems_days).values  # sums to 1 -> cumulative = beta
t_years = (ems_days - START).days.values / 365.25
season = np.cos(2 * np.pi * (ems_days.dayofyear.values - 15) / 365.25)
dow = ems_days.dayofweek.values
dow_eff = np.where(dow >= 5, -0.06, 0.0) + np.where(dow == 0, 0.04, 0.0)
day_noise = rng.gamma(90, 1 / 90, nd)
base = (TOTAL_PER_DAY * np.exp(0.02 * t_years + dow_eff) * day_noise)[:, None] * share[None, :] \
    * np.exp(wamp[None, :] * season[:, None])
heat = beta[None, :] * H[:, None]                                          # nd x nt
lam = base[:, :, None] * zw[None, None, :] * np.exp(heat[:, :, None] * zv[None, None, :])
counts = rng.poisson(lam)
lam_city = lam.sum(axis=2)                                                  # nd x nt, with heat
lam_noheat = base * 1.0                                                     # nd x nt, heat removed
pd.DataFrame({"date": np.repeat(ems_days, len(NAMES)), "call_type": np.tile(NAMES, nd),
              "lam_full": lam_city.ravel(), "lam_noheat": lam_noheat.ravel()}).to_csv(
    OUT / "true_expected.csv.gz", index=False, compression="gzip")                                                  # nd x nt x nz

# last day is partial (to 03:00)
counts[-1] = rng.binomial(counts[-1], 3 / 24)

d_i, t_i, z_i = np.nonzero(counts)
rep = counts[d_i, t_i, z_i]
d_i, t_i, z_i = np.repeat(d_i, rep), np.repeat(t_i, rep), np.repeat(z_i, rep)
n = len(d_i)
secs = rng.integers(0, 86400, n)
secs[d_i == nd - 1] = rng.integers(0, 3 * 3600, (d_i == nd - 1).sum())
ts = ems_days.values[d_i] + secs.astype("timedelta64[s]")
order = np.argsort(ts, kind="stable")
d_i, t_i, z_i, ts = d_i[order], t_i[order], z_i[order], ts[order]

sev_mean = np.array([TYPES[t][3] for t in NAMES])
sev = np.clip(np.round(sev_mean[t_i] + rng.normal(0, 0.8, n)), 1, 8).astype(int)
init_t = t_i.copy()
swap = rng.random(n) < 0.15
init_t[swap] = rng.choice([NAMES.index("SICK"), NAMES.index("OTHER"), NAMES.index("UNC")], swap.sum())
resp = np.round(rng.lognormal(np.log(560), 0.45, n)).astype(int)
transport = rng.random(n) < 0.68

truth = dict(T_ref=T_REF, logrr_per_degC={t: TYPES[t][1] for t in NAMES},
             vulnerable_zips=vuln_list, vuln_multiplier_on_log_effect=1.5, heat_waves=waves,
             today=str(TODAY.date()), rows=int(n))
(OUT / "truth.json").write_text(json.dumps(truth, indent=2))


def fmt_iso(t):
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%S.000")


def record(k, iid):
    t0 = pd.Timestamp(ts[k])
    on = t0 + pd.Timedelta(seconds=int(resp[k]))
    r = {
        "incident_id": str(iid), "incident_datetime": fmt_iso(t0),
        "initial_call_type": NAMES[init_t[k]], "initial_severity_level_code": str(sev[k]),
        "final_call_type": NAMES[t_i[k]], "final_severity_level_code": str(sev[k]),
        "first_assignment_datetime": fmt_iso(t0 + pd.Timedelta(seconds=int(resp[k] * 0.3))),
        "valid_dispatch_rspns_time_indc": "Y", "dispatch_response_seconds_qy": str(int(resp[k] * 0.3)),
        "first_activation_datetime": fmt_iso(t0 + pd.Timedelta(seconds=int(resp[k] * 0.4))),
        "first_on_scene_datetime": fmt_iso(on), "valid_incident_rspns_time_indc": "Y",
        "incident_response_seconds_qy": str(int(resp[k])),
        "incident_travel_tm_seconds_qy": str(int(resp[k] * 0.6)),
        "held_indicator": "N", "incident_disposition_code": "82" if transport[k] else "90",
        "borough": zboro[z_i[k]], "incident_dispatch_area": "X1", "zipcode": zcode[z_i[k]],
        "reopen_indicator": "N", "special_event_indicator": "N", "standby_indicator": "N",
        "transfer_indicator": "N",
    }
    if transport[k]:
        r["first_to_hosp_datetime"] = fmt_iso(on + pd.Timedelta(minutes=12))
        r["first_hosp_arrival_datetime"] = fmt_iso(on + pd.Timedelta(minutes=25))
    r["incident_close_datetime"] = fmt_iso(on + pd.Timedelta(minutes=55))
    return r


def write_json(path, idx, id0):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write("[\n")
        for j, k in enumerate(idx):
            if j:
                f.write(",\n")
            f.write(json.dumps(record(k, id0 + k)))
        f.write("\n]\n")


years = pd.DatetimeIndex(ts).year
hist_idx = np.where(years <= 2024)[0]
upd_idx = np.where(years == 2025)[0]
write_json(OUT / "ems_2021_2024.json.gz", hist_idx, 50_000_000)
write_json(OUT / "ems_2025_update.json.gz", upd_idx, 50_000_000)

# CSV-export style (upper-case spaced headers, US datetime) for July 2024, used for a format test
jul = np.where((pd.DatetimeIndex(ts) >= "2024-07-01") & (pd.DatetimeIndex(ts) < "2024-08-01"))[0]
rows = []
for k in jul:
    r = record(k, 50_000_000 + k)
    r = {("CAD_INCIDENT_ID" if c == "incident_id" else c.upper()): v for c, v in r.items()}
    for c in list(r):
        if c.endswith("DATETIME") and r[c]:
            r[c] = pd.Timestamp(r[c]).strftime("%m/%d/%Y %I:%M:%S %p")
    rows.append(r)
pd.DataFrame(rows).to_csv(OUT / "ems_2024_07_export.csv", index=False)
print(f"{n:,} synthetic records; {len(waves)} heat waves; files in {OUT}")
