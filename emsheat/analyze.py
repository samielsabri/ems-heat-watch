"""Run the analysis on an ingested store and write tables + figures + report."""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import model as M
from .ingest import last_complete_day, load_store
from .syndromes import HEAT_SYNDROME

COVID_EXCLUDE = [("2020-03-01", "2020-07-31")]


def daily_wide(t, field="final", col="n", end=None):
    d = t[t["field"] == field]
    w = d.pivot_table(index="date", columns="call_type", values=col, aggfunc="sum", fill_value=0)
    idx = pd.date_range(w.index.min(), end or w.index.max())
    return w.reindex(idx, fill_value=0)


def run(store, wx, out, train_end=None, eval_start=None, asof=None, exposure="tmax",
        heat_regex=r"HEAT|ENVIR", train_years=3, alpha=0.005, wave_thresh=32.2, log=print):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    t, z, state = load_store(store)
    last = last_complete_day(state, t)
    asof = pd.Timestamp(asof).normalize() if asof else pd.Timestamp.today().normalize()
    temp = wx[exposure].astype(float)

    wide = M.merge_variants(daily_wide(t, "final", "n", last))
    hi = daily_wide(t, "final", "hi", last).sum(axis=1)
    first = wide.index.min()
    eval_start = pd.Timestamp(eval_start) if eval_start else max(first + pd.DateOffset(years=train_years),
                                                                  last - pd.DateOffset(years=2))
    train_end = pd.Timestamp(train_end) if train_end else eval_start - pd.Timedelta(days=1)
    log(f"Data {first.date()} to {last.date()} (last complete day); train <= {train_end.date()}, "
        f"evaluate {eval_start.date()} to {last.date()}")
    missing_wx = wide.index.difference(temp.dropna().index)
    if len(missing_wx):
        log(f"WARNING: {len(missing_wx)} days without temperature; they are dropped from fits")

    # 1. threshold on all calls (training)
    allc = wide.sum(axis=1)
    T0, devs = M.choose_T0(allc[:train_end], temp, exclude=COVID_EXCLUDE)
    log(f"Heat threshold T0 = {T0} C (profile deviance, all calls, training period)")

    tnorm = M.normal_temp(temp, train_end)

    # 2. screen call types (training only; exploratory). Only codes used throughout training.
    stable = M.stable_types(wide, train_end)
    screen = M.screen_call_types({c: wide[c] for c in stable}, temp, T0, train_end,
                                 exclude=COVID_EXCLUDE)
    coded = [c for c in wide.columns if re.search(heat_regex, c)]
    sens = screen[(screen["q"] < 0.05) & (screen["rr"] >= 1.02)]["call_type"].tolist()
    # the syndrome outcome is pre-specified, not taken from the screen
    syndrome = [c for c in HEAT_SYNDROME if c in wide.columns and c not in coded]
    log(f"Heat-coded call types: {coded or 'none found'}; heat-sensitive (q<0.05): {sens}")

    outcomes = {}
    if coded and wide[coded].sum(axis=1)[:train_end].mean() >= 0.3:
        outcomes["Heat-coded calls"] = dict(y=wide[coded].sum(axis=1), types=coded)
    if syndrome:
        outcomes["Heat syndrome (pre-specified)"] = dict(y=wide[syndrome].sum(axis=1), types=syndrome)
    outcomes["All EMS calls"] = dict(y=allc, types=list(wide.columns))
    outcomes["Life-threatening (segments 1-3)"] = dict(y=hi, types=None)
    primary = next(iter(outcomes))

    # 3. exposure-response, surveillance, backtest, forecast per outcome
    events = M.heat_events(temp[first:last], wave_thresh)
    results = {}
    for name, o in outcomes.items():
        y = o["y"]
        T0o, _ = M.choose_T0(y[:train_end], temp, exclude=COVID_EXCLUDE)
        retro = M.HeatModel("retro", T0o).fit(y[:train_end], temp, COVID_EXCLUDE)
        c, se = retro.cumulative()
        surv = M.surveil(y, temp, eval_start, last, T0o, train_years, 7, alpha, COVID_EXCLUDE, tnorm)
        ev_eval = events[events["start"] >= eval_start] if len(events) else events
        bt = M.backtest_events(surv, ev_eval)
        fc = M.forecast(y[:last], temp, T0o, train_years, COVID_EXCLUDE)
        if fc is not None:
            fc = fc[fc.index > last]
        results[name] = dict(T0=T0o, logrr=c, se=se, rr=np.exp(c), rr_lo=np.exp(c - 1.96 * se),
                             rr_hi=np.exp(c + 1.96 * se), phi=retro.phi, mean_daily=float(y[:train_end].mean()),
                             retro=retro, surv=surv, backtest=bt, forecast=fc, types=o["types"])
        surv.to_csv(out / f"surveillance_{_slug(name)}.csv")
        bt.to_csv(out / f"backtest_{_slug(name)}.csv", index=False)
        log(f"  {name}: RR per degC above {T0o} = {np.exp(c):.3f} "
            f"({np.exp(c - 1.96 * se):.3f}-{np.exp(c + 1.96 * se):.3f}); "
            f"{int(surv['alarm'].sum())} alarm days in evaluation")

    # 4. zip ratios for evaluated heat waves (primary outcome)
    # zip counts of heat-coded calls alone are too sparse, so pool coded + heat-sensitive types
    zres, zip_types = {}, sorted(set(coded) | set(syndrome)) or list(wide.columns)
    if z is not None and len(events):
        yz = wide[zip_types].sum(axis=1)
        T0z, _ = M.choose_T0(yz[:train_end], temp, exclude=COVID_EXCLUDE)
        survz = M.surveil(yz, temp, eval_start, last, T0z, train_years, 7, alpha, COVID_EXCLUDE, tnorm)
        for _, e in events[events["start"] >= eval_start].iterrows():
            if e["end"] + pd.Timedelta(days=3) > last:
                continue
            try:
                zr = M.zip_ratios(z, zip_types, survz, e, temp, T0z)
                zres[str(e["start"].date())] = zr
                zr.to_csv(out / f"zip_ratios_{e['start'].date()}.csv")
            except Exception as ex:  # noqa: BLE001
                log(f"  zip ratios skipped for {e['start'].date()}: {ex}")

    pooled = M.pool_zip_ratios(zres)
    if pooled is not None:
        pooled.to_csv(out / "zip_ratios_pooled.csv")
    screen.to_csv(out / "call_type_screen.csv", index=False)
    events.to_csv(out / "heat_waves.csv", index=False)

    fresh = dict(watermark=state.get("watermark"), last_complete=str(last.date()), asof=str(asof.date()),
                 lag_days=int((asof - last).days),
                 visible_with_6mo_lag=int((events["end"] <= asof - pd.Timedelta(days=182)).sum()) if len(events) else 0,
                 visible_now=int((events["end"] <= last).sum()) if len(events) else 0)
    ctx = dict(zip_pooled=pooled, zip_types=zip_types, T0=T0, devs=devs, screen=screen, coded=coded, sens=sens, outcomes=outcomes, primary=primary,
               results=results, events=events, zres=zres, fresh=fresh, eval_start=eval_start,
               train_end=train_end, last=last, first=first, temp=temp, alpha=alpha, state=state)
    summary = {k: {kk: (float(vv) if isinstance(vv, (np.floating, float)) else vv)
                   for kk, vv in r.items() if kk in ("T0", "rr", "rr_lo", "rr_hi", "phi", "mean_daily")}
               for k, r in results.items()}
    (out / "summary.json").write_text(json.dumps(dict(freshness=fresh, outcomes=summary,
                                                      heat_coded=coded, heat_sensitive=sens), indent=2,
                                                 default=str))
    return ctx


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
