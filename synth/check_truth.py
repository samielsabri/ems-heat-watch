"""Compare pipeline output on synthetic data with the known truth."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
rep = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "report")
syn = ROOT / "data" / "synthetic"
truth = json.loads((syn / "truth.json").read_text())
te = pd.read_csv(syn / "true_expected.csv.gz", parse_dates=["date"])
summ = json.loads((rep / "summary.json").read_text())

print("1. Call-type screen (training period)")
true_pos = {k for k, v in truth["logrr_per_degC"].items() if v > 0}
found = set(summ["heat_sensitive"])
print(f"   true heat-sensitive: {sorted(true_pos)}")
print(f"   detected (q<0.05):   {sorted(found)}")
print(f"   missed: {sorted(true_pos - found)}  false positives: {sorted(found - true_pos)}")

outcomes = {"heat_coded_calls": summ["heat_coded"],
            "heat_sensitive_syndrome": [t for t in summ["heat_sensitive"] if t not in summ["heat_coded"]],
            "all_ems_calls": sorted(te["call_type"].unique())}
print("\n2. Model-expected vs true heat-attributable calls (evaluation period)")
print(f"   {'outcome':26s} {'true total':>10s} {'model':>8s} {'ratio':>6s} {'r(daily)':>8s} | alarm sens (true RR>1.25) / false alarm rate (true RR<1.02)")
for name, types in outcomes.items():
    f = rep / f"surveillance_{name}.csv"
    if not f.exists() or not types:
        continue
    s = pd.read_csv(f, index_col=0, parse_dates=True)
    t = te[te["call_type"].isin(types)].groupby("date")[["lam_full", "lam_noheat"]].sum().reindex(s.index)
    true_heat = t["lam_full"] - t["lam_noheat"]
    rr = t["lam_full"] / t["lam_noheat"]
    r = np.corrcoef(true_heat, s["heat_expected"])[0, 1]
    hot, cool = rr > 1.25, rr < 1.02
    sens = s.loc[hot, "alarm_excess"].mean() if hot.any() else np.nan
    far = s.loc[cool, "alarm_excess"].mean()
    print(f"   {name:26s} {true_heat.sum():10.0f} {s['heat_expected'].sum():8.0f} "
          f"{s['heat_expected'].sum() / true_heat.sum():6.2f} {r:8.3f} | {sens:.2f} ({hot.sum()} days) / {far:.4f} ({cool.sum()} days)")

print("\n3. Zip ratios: are the doubled-sensitivity zips at the top?")
vuln = set(truth["vulnerable_zips"])
for f in sorted(rep.glob("zip_ratios_*.csv")):
    z = pd.read_csv(f, dtype={"zipcode": str})
    z = z.sort_values("relative", ascending=False)
    k = len(vuln & set(z["zipcode"]))
    top = z.head(k)["zipcode"]
    lab = z["zipcode"].isin(vuln).astype(int).values
    ranks = pd.Series(z["relative"].values).rank().values
    auc = (ranks[lab == 1].sum() - k * (k + 1) / 2) / (k * (len(z) - k))
    print(f"   {f.stem[11:]}: {top.isin(vuln).sum()}/{k} vulnerable zips in top {k}; AUC {auc:.2f}")
