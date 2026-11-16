"""
Score detector output against simulated ground truth.

Metrics (per series, per detector), following Noufaily et al. 2013 / Bédubourg & Le Strat 2017:
- FPR          alarms in non-outbreak weeks / non-outbreak weeks (evaluation period)
- POD          share of outbreaks with >= 1 alarm during their outbreak weeks
- sensitivity  share of outbreak weeks that alarmed
- lag          weeks from outbreak start to first alarm (detected outbreaks only)
"""
import numpy as np
import pandas as pd


def score(det_out: pd.DataFrame, df: pd.DataFrame, outbreaks: pd.DataFrame) -> dict:
    d = det_out.merge(df[["week", "outbreak_cases"]], on="week")
    nonob = d["outbreak_cases"] == 0
    fpr = d.loc[nonob, "alarm"].mean() if nonob.any() else np.nan
    sens = d.loc[~nonob, "alarm"].mean() if (~nonob).any() else np.nan

    detected, lags = [], []
    alarm_weeks = set(d.loc[d["alarm"], "week"])
    for ob in outbreaks[outbreaks["in_eval"]].itertuples():
        ob_weeks = set(df.loc[df["outbreak_id"] == ob.outbreak_id, "week"])
        hits = sorted(alarm_weeks & ob_weeks)
        detected.append(bool(hits))
        if hits:
            lags.append(hits[0] - ob.start)
    return dict(
        fpr=fpr,
        sensitivity=sens,
        pod=np.mean(detected) if detected else np.nan,
        mean_lag=np.mean(lags) if lags else np.nan,
        n_outbreaks=len(detected),
        n_detected=int(np.sum(detected)),
    )
