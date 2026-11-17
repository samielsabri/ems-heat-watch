"""
Back-test alarm methods against temperature-defined heat waves.

Heat wave: >= 3 consecutive days with Central Park Tmax >= 32.2 C (90 F).

Per method and period:
  POD          share of heat waves with >= 1 alarm from onset to the last hot day
  median/mean days to first alarm (0 = alarm on the onset day), detected waves only
  FAR          alarm days / non-heat days in the warm season (May-Sep)
               non-heat day: Tmax < 29.4 C (85 F) that day and the 3 days before, and
               not within [onset - 3, end + 7] of any heat wave
  FA/season    false alarms per warm season (same days, scaled to 153 days)
  hot-day alarm rate: alarms on isolated hot days (Tmax >= 32.2 outside any wave), reported
               separately because heat-coded calls legitimately rise on them.
Mar-Jul 2020 (COVID) is dropped from scoring.
"""
import numpy as np
import pandas as pd

from .model import heat_events

COVID = ("2020-03-01", "2020-07-31")


def day_classes(temp, events, hot=32.2, cool=29.4, pre=3, post=7):
    idx = temp.index
    cls = pd.Series("other", index=idx)
    near = pd.Series(False, index=idx)
    wave = pd.Series(False, index=idx)
    for _, e in events.iterrows():
        near[e["start"] - pd.Timedelta(days=pre): e["end"] + pd.Timedelta(days=post)] = True
        wave[e["start"]: e["end"]] = True
    recent_max = temp.rolling(4, min_periods=4).max()
    cls[(recent_max < cool) & ~near] = "nonheat"
    cls[(temp >= hot) & ~wave] = "hot_isolated"
    cls[wave] = "wave"
    warm = idx.month.isin([5, 6, 7, 8, 9])
    cls[~warm & (cls == "nonheat")] = "nonheat_cold_season"
    cov = (idx >= pd.Timestamp(COVID[0])) & (idx <= pd.Timestamp(COVID[1]))
    cls[cov] = "excluded"
    return cls


def score(alarms, temp, events, start, end):
    """alarms: bool Series by date. events: heat_events() output."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    a = alarms.astype(bool)[start:end]
    cls = day_classes(temp, events).reindex(a.index)
    ev = events[(events["start"] >= start) & (events["end"] <= end)]
    cov = (ev["start"] <= pd.Timestamp(COVID[1])) & (ev["end"] >= pd.Timestamp(COVID[0]))
    ev = ev[~cov]
    rows = []
    for _, e in ev.iterrows():
        w = a[e["start"]: e["end"]]
        first = w.index[w.values]
        rows.append(dict(start=e["start"].date(), end=e["end"].date(), days=e["days"], peak=e["peak"],
                         detected=len(first) > 0, alarm_days=int(w.sum()),
                         delay=(first[0] - e["start"]).days if len(first) else np.nan))
    per = pd.DataFrame(rows)
    nh = cls == "nonheat"
    hot = cls == "hot_isolated"
    det = per[per["detected"]] if len(per) else per
    summ = dict(
        waves=len(per), detected=int(per["detected"].sum()) if len(per) else 0,
        POD=per["detected"].mean() if len(per) else np.nan,
        median_delay=det["delay"].median() if len(det) else np.nan,
        mean_delay=det["delay"].mean() if len(det) else np.nan,
        wave_day_sens=a[cls == "wave"].mean() if (cls == "wave").any() else np.nan,
        nonheat_days=int(nh.sum()), false_alarms=int(a[nh].sum()),
        FAR=a[nh].mean() if nh.any() else np.nan,
        hot_isolated_days=int(hot.sum()), hot_isolated_alarm_rate=a[hot].mean() if hot.any() else np.nan,
    )
    summ["FA_per_season"] = summ["FAR"] * 153
    return summ, per


def compare(methods, temp, periods, thresh=32.2):
    """methods: {name: bool alarm Series}. periods: {label: (start, end)}."""
    events = heat_events(temp, thresh)
    rows, per_wave = [], {}
    for label, (s, e) in periods.items():
        for name, al in methods.items():
            summ, per = score(al, temp, events, s, e)
            rows.append(dict(period=label, method=name, **summ))
            per_wave[(label, name)] = per
    return pd.DataFrame(rows), per_wave, events
