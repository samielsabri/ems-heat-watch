"""
Is weak zip detection a method bug or low power? Simulate aggregated zip counts directly
(no record generation) at different daily volumes and score zip_ratios against the truth.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from emsheat import model as M  # noqa: E402

wx = pd.read_csv(Path(__file__).resolve().parent.parent / "data/synthetic/weather_synthetic.csv",
                 parse_dates=["date"]).set_index("date")["tmax"]
days = pd.date_range("2023-01-01", "2024-12-31")
pos = (wx - 27).clip(lower=0)
H = (0.6 * pos + 0.3 * pos.shift(1) + 0.1 * pos.shift(2)).reindex(days).values
beta = 0.035                                   # pooled heat-sensitive calls
nz = 158


def trial(per_day, seed):
    rng = np.random.default_rng(seed)
    w = rng.lognormal(0, 0.45, nz)
    w /= w.sum()
    vuln = np.zeros(nz, bool)
    vuln[rng.choice(nz, 16, replace=False)] = True
    v = np.where(vuln, 1.5, 1.0)
    season = 1 + 0.05 * np.cos(2 * np.pi * (days.dayofyear.values - 15) / 365.25)
    base = per_day * season
    lam = base[:, None] * w[None, :] * np.exp(beta * H[:, None] * v[None, :])
    cnt = rng.poisson(lam)
    zips = [f"Z{i:03d}" for i in range(nz)]
    zd = pd.DataFrame(cnt, index=days, columns=zips).stack().rename("n").reset_index()
    zd.columns = ["date", "zipcode", "n"]
    zd["call_type"] = "X"
    surv = pd.DataFrame({"mu_base": base, "obs": cnt.sum(1)}, index=days)
    ev = M.heat_events(wx.reindex(days), 32.2)
    ev = ev[ev["start"].dt.year == 2024]
    zrs = {str(e["start"].date()): M.zip_ratios(zd, ["X"], surv, e, wx, 27.5) for _, e in ev.iterrows()}
    p = M.pool_zip_ratios(zrs)
    lab = p.index.isin([zips[i] for i in np.where(vuln)[0]]).astype(int)
    r = pd.Series(p["relative"].values).rank().values
    k = lab.sum()
    return (r[lab == 1].sum() - k * (k + 1) / 2) / (k * (len(p) - k)), len(ev)


for per_day in (150, 600, 1500, 4000):
    aucs = [trial(per_day, s)[0] for s in range(20)]
    print(f"{per_day:5d} heat-sensitive calls/day citywide: pooled zip AUC {np.mean(aucs):.2f} "
          f"(range {min(aucs):.2f}-{max(aucs):.2f}, 20 runs)")
