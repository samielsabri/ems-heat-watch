"""
v2 real-data back-test (NYC, HEAT + pre-specified heat syndrome).

  python analysis/run_v2.py --store store --weather-csv data/central_park_tmax.csv --out results/v2

Changes from v1, fixed after reviewing v1 and before any v2 output was seen:
  1. Heat-model alarm compares observed calls with the NB 99.5% limit of the count expected at the
     climatological normal Tmax for the date (normal fitted on Tmax <= 2024), not with the heat-
     zeroed baseline. Secondary row: "unexplained" alarm (obs above what the heat model expects
     given the observed temperature).
  2. Syndrome is pre-specified (emsheat/syndromes.py), code variants merged. The screen is
     exploratory only, restricted to codes used throughout training, with q < 0.05 and >= +2%/C,
     and degenerate fits dropped.
  3. T0 profile grid 15-33 C.

Design (fixed before looking at 2025-26):
  development period   2016-01-01 .. 2024-12-31   (T0, call-type screen and any tuning use <= 2024)
  held-out evaluation  2025-01-01 .. last complete day
  heat wave            >= 3 consecutive days Central Park Tmax >= 32.2 C
  methods              heat model (prospective, weekly refit, 3 training years, NB 99.5% limit
                       of the no-heat seasonal expectation), EARS C1/C2/C3, Farrington Flexible
                       (alpha 0.005). All default parameters; nothing tuned.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emsheat import aberration as A  # noqa: E402
from emsheat import backtest as B  # noqa: E402
from emsheat import model as M  # noqa: E402
from emsheat.analyze import COVID_EXCLUDE, daily_wide  # noqa: E402
from emsheat.ingest import last_complete_day, load_store  # noqa: E402
from emsheat.syndromes import HEAT_SYNDROME  # noqa: E402

DEV = ("2016-01-01", "2024-12-31")
TRAIN_END = "2024-12-31"
EVAL_START = "2025-01-01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="store")
    ap.add_argument("--weather-csv", required=True)
    ap.add_argument("--out", default="results/v2")
    ap.add_argument("--alpha", type=float, default=0.005)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    t, z, state = load_store(a.store)
    last = last_complete_day(state, t)
    wx = pd.read_csv(a.weather_csv, parse_dates=["date"]).set_index("date").sort_index()
    temp = wx["tmax"].astype(float)
    wide = M.merge_variants(daily_wide(t, "final", "n", last))
    wide_init = daily_wide(t, "initial", "n", last)
    log = {}

    # ---------------- data QA ----------------
    yr = wide.index.year
    qa = pd.DataFrame({
        "all_calls": wide.sum(axis=1).groupby(yr).sum(),
        "HEAT_final": wide.get("HEAT", 0).groupby(yr).sum(),
        "HEAT_initial": wide_init.get("HEAT", 0).groupby(yr).sum(),
        "days": wide.groupby(yr).size(),
        "days_tmax_ge_32.2": (temp.reindex(wide.index) >= 32.2).groupby(yr).sum(),
        "HEAT_max_day": wide.get("HEAT", 0).groupby(yr).max(),
    })
    qa["HEAT_per_1e5_calls"] = 1e5 * qa["HEAT_final"] / qa["all_calls"]
    qa.to_csv(out / "qa_by_year.csv")
    # other plausibly heat-labelled codes: look for anything with HEAT/ENVIR/HYPER in its name
    cand = [c for c in wide.columns if re.search(r"HEAT|ENVIR|HYPER|DEHYD", c)]
    wide[cand].groupby(yr).sum().to_csv(out / "qa_heatlike_codes_by_year.csv")
    log["heatlike_codes"] = cand
    # HEAT by month (seasonality / out-of-season use)
    wide["HEAT"].groupby([yr, wide.index.month]).sum().unstack(fill_value=0).to_csv(out / "qa_heat_by_month.csv")
    # initial->final agreement for HEAT (how many HEAT final calls started as something else is not
    # available from daily aggregates; we report initial vs final totals only)

    # ---------------- exposure-response + screen (<= 2024) ----------------
    allc = wide.sum(axis=1)
    T0_all, _ = M.choose_T0(allc[:TRAIN_END], temp, exclude=COVID_EXCLUDE)
    stable = M.stable_types(wide, TRAIN_END)
    screen = M.screen_call_types({c: wide[c] for c in stable}, temp, T0_all, TRAIN_END,
                                 exclude=COVID_EXCLUDE)
    screen.to_csv(out / "call_type_screen.csv", index=False)
    sens = screen[(screen["q"] < 0.05) & (screen["rr"] >= 1.02)]["call_type"].tolist()
    syndrome = list(HEAT_SYNDROME)
    log["stable_types_n"] = len(stable)
    log["dropped_unstable"] = sorted(set(c for c in wide.columns if wide[c][:TRAIN_END].mean() >= 1) - set(stable))
    log.update(T0_all_calls=T0_all, heat_sensitive=sens, syndrome=syndrome)

    outcomes = {"HEAT": wide["HEAT"], "Heat syndrome (pre-specified)": wide[syndrome].sum(axis=1),
                "All calls": allc}
    er = []
    for name, y in outcomes.items():
        T0, devs = M.choose_T0(y[:TRAIN_END], temp, exclude=COVID_EXCLUDE)
        m = M.HeatModel("retro", T0).fit(y[:TRAIN_END], temp, COVID_EXCLUDE)
        c, se = m.cumulative()
        lag = m.lag_effects()
        er.append(dict(outcome=name, T0=T0, rr=np.exp(c), lo=np.exp(c - 1.96 * se), hi=np.exp(c + 1.96 * se),
                       phi=m.phi, mean_daily=float(y[:TRAIN_END].mean()),
                       rr_lag0=np.exp(lag.loc["h0", "logrr"]), rr_lag1=np.exp(lag.loc["h1", "logrr"]),
                       rr_lag23=np.exp(lag.loc["h23", "logrr"]), T0_at_grid_edge=T0 in (devs.index.min(), devs.index.max())))
        devs.to_csv(out / f"T0_profile_{_slug(name)}.csv")
    er = pd.DataFrame(er)
    er.to_csv(out / "exposure_response.csv", index=False)

    tnorm = M.normal_temp(temp, TRAIN_END)
    tnorm.to_csv(out / "normal_tmax.csv")

    # ---------------- surveillance + detectors ----------------
    start, end = DEV[0], last
    alarms_by_outcome, summaries, waves = {}, [], []
    for name in ("HEAT", "Heat syndrome (pre-specified)"):
        y = outcomes[name]
        T0 = float(er.loc[er["outcome"] == name, "T0"].iloc[0])
        surv = M.surveil(y, temp, start, end, T0, 3, 7, a.alpha, COVID_EXCLUDE, tnorm)
        surv.to_csv(out / f"surveillance_{_slug(name)}.csv")
        dets = A.run_all(y, start, end, a.alpha, COVID_EXCLUDE)
        methods = {"Heat model vs normal Tmax": surv["alarm_norm"],
                   "Heat model, unexplained": surv["alarm_unexplained"]}
        methods.update({k: v["alarm"] for k, v in dets.items()})
        for k, v in dets.items():
            v.to_csv(out / f"detector_{_slug(name)}_{_slug(k)}.csv")
        alarms = pd.DataFrame(methods)
        alarms.to_csv(out / f"alarms_{_slug(name)}.csv")
        alarms_by_outcome[name] = alarms
        summ, per, events = B.compare(methods, temp[:end], {"Development 2016-2024": DEV,
                                                              f"Held-out 2025-{last:%Y-%m-%d}": (EVAL_START, end)})
        summ.insert(0, "outcome", name)
        summaries.append(summ)
        for (period, meth), p in per.items():
            if len(p):
                waves.append(p.assign(outcome=name, period=period, method=meth))
    events.to_csv(out / "heat_waves.csv", index=False)
    summary = pd.concat(summaries, ignore_index=True)
    summary.to_csv(out / "backtest_summary.csv", index=False)
    pd.concat(waves, ignore_index=True).to_csv(out / "backtest_per_wave.csv", index=False)

    # false-alarm clusters: non-heat alarm days by month, per method, HEAT
    cls = B.day_classes(temp, events).reindex(alarms_by_outcome["HEAT"].index)
    fa = alarms_by_outcome["HEAT"][cls == "nonheat"]
    fa = fa[fa.any(axis=1)]
    fa.assign(tmax=temp.reindex(fa.index), heat=wide["HEAT"].reindex(fa.index)).to_csv(out / "false_alarm_days_HEAT.csv")

    log.update(last_complete=str(last.date()), watermark=state.get("watermark"),
               store_source=state.get("source"), alpha=a.alpha, dev=DEV, eval_start=EVAL_START)
    (out / "run_log.json").write_text(json.dumps(log, indent=2, default=str))
    pd.set_option("display.width", 200)
    print(qa.to_string())
    print(er.to_string())
    print("heat-sensitive:", sens)
    print(summary[["outcome", "period", "method", "waves", "detected", "POD", "median_delay", "FAR",
                   "FA_per_season", "hot_isolated_alarm_rate"]].to_string())


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


if __name__ == "__main__":
    main()
