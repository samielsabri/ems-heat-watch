"""
Run all detectors prospectively on a real weekly surveillance series.

Input formats
-------------
1. Long CSV:   columns  year, week, cases        (--format long)
2. SurvStat@RKI export, rows = Meldejahr, columns = Meldewoche   (--format survstat)
   SurvStat downloads are usually UTF-16, tab-separated; the loader tries
   UTF-16 then UTF-8. Check the first rows of your file if parsing fails.

ISO weeks are kept as one consecutive series; in 53-week years the 52-week
seasonal cycle drifts by one week, which is negligible for Farrington's
±3-week reference window.

Usage:
    python src/run_real.py --csv data/salmonellosis_de.csv --format survstat \
        --eval-weeks 104 --label "Salmonellosis, Germany" --out results/real/
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from detectors import DETECTORS
from run_simulation import COLORS


def load_long(path):
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    return df[["year", "week", "cases"]].astype(int)


def load_survstat(path):
    raw = None
    for enc in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            raw = pd.read_csv(path, sep="\t", encoding=enc, header=0)
            break
        except (UnicodeError, pd.errors.ParserError):
            continue
    if raw is None:
        raise ValueError(f"Could not parse {path}")
    raw = raw.rename(columns={raw.columns[0]: "year"})
    raw = raw[pd.to_numeric(raw["year"], errors="coerce").notna()]  # drop header/total rows
    week_cols = [c for c in raw.columns[1:] if str(c).strip().isdigit()]
    long = raw.melt(id_vars="year", value_vars=week_cols, var_name="week", value_name="cases")
    long["year"] = long["year"].astype(int)
    long["week"] = long["week"].astype(int)
    long["cases"] = pd.to_numeric(long["cases"], errors="coerce")
    return long.dropna(subset=["cases"]).astype({"cases": int})


def to_series(long):
    long = long.sort_values(["year", "week"]).reset_index(drop=True)
    # drop week 53 in years that don't have one (SurvStat pads with empty cells)
    valid = long.apply(lambda r: r.week <= pd.Timestamp(r.year, 12, 28).isocalendar()[1], axis=1)
    long = long[valid].reset_index(drop=True)
    long["week_start"] = pd.to_datetime(
        long["year"].astype(str) + "-W" + long["week"].astype(str).str.zfill(2) + "-1",
        format="%G-W%V-%u")
    return long


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--format", choices=["long", "survstat"], default="long")
    ap.add_argument("--eval-weeks", type=int, default=104)
    ap.add_argument("--label", default="Weekly cases")
    ap.add_argument("--out", type=Path, default=Path("results/real"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    long = load_long(a.csv) if a.format == "long" else load_survstat(a.csv)
    s = to_series(long)
    y = s["cases"].to_numpy()
    need = 5 * 52 + 3 + a.eval_weeks
    if len(y) < need:
        raise SystemExit(f"Need >= {need} weeks for Farrington (b=5); have {len(y)}.")
    eval_idx = np.arange(len(y) - a.eval_weeks, len(y))

    alarms = []
    fig, axes = plt.subplots(len(DETECTORS), 1, figsize=(11, 2.3 * len(DETECTORS)), sharex=True)
    ev = s.iloc[eval_idx]
    for ax, (dname, det) in zip(axes, DETECTORS.items()):
        out = det(y, eval_idx)
        out["week_start"] = s["week_start"].to_numpy()[out["week"]]
        out["detector"] = dname
        alarms.append(out)
        ax.bar(ev["week_start"], ev["cases"], width=6, color="#bdbdbd")
        ax.step(out["week_start"], out["threshold"], where="mid", color=COLORS[dname], lw=1.4)
        a_ = out[out["alarm"]]
        ax.scatter(a_["week_start"], a_["observed"] * 1.05 + 1, marker="v", color="red", s=25, zorder=5)
        ax.set_title(f"{dname}  ({int(out['alarm'].sum())} alarms)", loc="left", fontsize=10)
    axes[0].set_title(a.label, loc="right", fontsize=10)
    fig.tight_layout()
    fig.savefig(a.out / "real_alarms.png", dpi=150)

    res = pd.concat(alarms)[["detector", "week_start", "observed", "expected", "threshold", "alarm"]]
    res.to_csv(a.out / "real_alarms.csv", index=False)
    # agreement table: which weeks were flagged by how many methods
    wide = res.pivot(index="week_start", columns="detector", values="alarm")
    wide["n_methods"] = wide.sum(axis=1)
    wide[wide["n_methods"] > 0].to_csv(a.out / "alarm_agreement.csv")
    print(res.groupby("detector")["alarm"].sum())


if __name__ == "__main__":
    main()
