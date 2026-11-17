"""
Heat models for daily EMS call counts.

Two model forms share one design:

  retro   log E[Y_t] = a + s(time) + DOW + holiday + heat(T)
          s(time) is a natural cubic spline with ~7 df/year (the standard time-series
          approach for temperature-health studies). Used to estimate the exposure-
          response and to screen call types. Cannot extrapolate past the data.

  prosp   log E[Y_t] = a + b*trend + 3 harmonic pairs + DOW + holiday + heat(T)
          Fit on a rolling window of past years only, then predicts forward. This is
          the surveillance model: it needs nothing from the future except temperature
          (observed, or forecast).

heat(T) is a threshold ("hockey-stick") term with constrained lags:
    h0  = max(T_t - T0, 0)
    h1  = max(T_{t-1} - T0, 0)
    h23 = mean(max(T_{t-2} - T0, 0), max(T_{t-3} - T0, 0))
so exp(b0 + b1 + b23) is the cumulative rate ratio per degree above T0 for sustained heat.
T0 is chosen by profile deviance. A full DLNM (R package dlnm) is the natural upgrade.

Fits are quasi-Poisson (Poisson GLM, scale from Pearson chi2). Alarm thresholds use a
negative binomial with the same mean and variance phi*mu.
"""
import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
from pandas.tseries.holiday import USFederalHolidayCalendar
from scipy import stats

HEAT = ["h0", "h1", "h23"]


def heat_terms(temp, T0):
    pos = (temp - T0).clip(lower=0)
    return pd.DataFrame({"h0": pos, "h1": pos.shift(1),
                         "h23": (pos.shift(2) + pos.shift(3)) / 2}, index=temp.index)


def base_terms(dates, mode, origin, df_per_year=7):
    X = pd.DataFrame(index=dates)
    X["const"] = 1.0
    dow = dates.dayofweek
    for k in range(1, 7):
        X[f"dow{k}"] = (dow == k).astype(float)
    hol = USFederalHolidayCalendar().holidays(dates.min() - pd.Timedelta(days=1), dates.max() + pd.Timedelta(days=1))
    X["holiday"] = dates.isin(hol).astype(float)
    t = np.asarray((dates - origin).days, dtype=float) / 365.25
    if mode == "retro":
        years = (t.max() - t.min()) + 1 / 365.25
        k = max(4, int(round(df_per_year * years)))
        S = patsy.dmatrix(f"cr(t, df={k}, constraints='center') - 1", {"t": t}, return_type="matrix")
        for j in range(S.shape[1]):
            X[f"s{j}"] = np.asarray(S)[:, j]
    else:
        X["trend"] = t
        ang = 2 * np.pi * dates.dayofyear.values / 365.25
        for k in (1, 2, 3):
            X[f"sin{k}"] = np.sin(k * ang)
            X[f"cos{k}"] = np.cos(k * ang)
    return X


def nb_upper(mu, phi, alpha):
    """Upper (1-alpha) quantile of a count with mean mu and variance phi*mu."""
    mu = np.asarray(mu, dtype=float)
    if phi <= 1.0001:
        return stats.poisson.ppf(1 - alpha, mu)
    r = mu / (phi - 1)
    return stats.nbinom.ppf(1 - alpha, r, r / (r + mu))


class HeatModel:
    def __init__(self, mode="retro", T0=27.0, df_per_year=7):
        self.mode, self.T0, self.df_per_year = mode, T0, df_per_year

    def _X(self, dates, temp):
        X = base_terms(dates, self.mode, self.origin, self.df_per_year)
        H = heat_terms(temp, self.T0).reindex(dates)
        return pd.concat([X, H], axis=1)

    def fit(self, y, temp, exclude=None):
        """y: daily counts (DatetimeIndex). temp: daily temperature covering y (+3 prior days)."""
        y = y.astype(float)
        self.origin = y.index.min()
        X = self._X(y.index, temp)
        ok = X.notna().all(axis=1) & y.notna()
        for a, b in exclude or []:
            ok &= ~((y.index >= pd.Timestamp(a)) & (y.index <= pd.Timestamp(b)))
        self.n_obs = int(ok.sum())
        self.res = sm.GLM(y[ok], X[ok], family=sm.families.Poisson()).fit(scale="X2")
        self.phi = float(self.res.scale)
        self.cols = X.columns
        return self

    @property
    def deviance(self):
        return float(self.res.deviance)

    def predict(self, dates, temp):
        """Expected counts with heat (mu_full) and with heat terms zeroed (mu_base)."""
        X = self._X(pd.DatetimeIndex(dates), temp)[self.cols]
        b = self.res.params
        eta = X.fillna(0).values @ b.values
        heat = X[HEAT].fillna(0).values @ b[HEAT].values
        return pd.DataFrame({"mu_full": np.exp(eta), "mu_base": np.exp(eta - heat)}, index=X.index)

    def cumulative(self):
        """Cumulative log-RR per degC above T0 (sustained heat) and its SE."""
        b, V = self.res.params[HEAT], self.res.cov_params().loc[HEAT, HEAT]
        return float(b.sum()), float(np.sqrt(V.values.sum()))

    def lag_effects(self):
        b, se = self.res.params[HEAT], self.res.bse[HEAT]
        return pd.DataFrame({"logrr": b, "se": se})

    def curve(self, temps):
        c, se = self.cumulative()
        x = np.clip(np.asarray(temps) - self.T0, 0, None)
        return pd.DataFrame({"temp": temps, "rr": np.exp(c * x),
                             "lo": np.exp((c - 1.96 * se) * x), "hi": np.exp((c + 1.96 * se) * x)})


def choose_T0(y, temp, grid=np.arange(15, 33.5, 0.5), exclude=None):
    devs = []
    for T0 in grid:
        try:
            devs.append(HeatModel("retro", T0).fit(y, temp, exclude).deviance)
        except Exception:  # noqa: BLE001
            devs.append(np.inf)
    devs = np.array(devs)
    return float(grid[int(np.argmin(devs))]), pd.Series(devs, index=grid)


def merge_variants(wide, suffixes=("FC", "FT", "RF")):
    """Fold suffixed code variants (e.g. SICKFC, used 2020-23) into their base code when the
    base code exists. Returns a new wide frame."""
    out = wide.copy()
    for c in list(out.columns):
        for suf in suffixes:
            base = c[: -len(suf)]
            if c.endswith(suf) and base in out.columns and base != c:
                out[base] = out[base] + out[c]
                out = out.drop(columns=c)
                break
    return out


def stable_types(wide, train_end, exclude_years=(2020,), min_share=0.25):
    """Codes used throughout training: every full training year (except exclude_years) has at
    least min_share of the median annual count. Drops codes introduced, retired or split."""
    w = wide[:train_end]
    yr = w.groupby(w.index.year).sum()
    yr = yr[(w.groupby(w.index.year).size() >= 360).values]
    yr = yr.drop(index=[y for y in exclude_years if y in yr.index])
    med = yr.median()
    ok = (yr >= min_share * med).all() & (med > 0)
    return list(ok[ok].index)


def screen_call_types(daily_by_type, temp, T0, train_end, min_daily=1.0, exclude=None):
    """
    Fit the retro model to each call type (training period only) and rank by heat
    sensitivity. Returns RR per degC above T0 with CI and Benjamini-Hochberg q-values.
    Selecting on training years and evaluating later avoids circular validation.
    """
    rows = []
    for ct, y in daily_by_type.items():
        y = y[:train_end]
        if y.mean() < min_daily:
            continue
        try:
            m = HeatModel("retro", T0).fit(y, temp, exclude)
        except Exception:  # noqa: BLE001
            continue
        c, se = m.cumulative()
        if not (np.isfinite(c) and np.isfinite(se) and se > 1e-4):
            continue  # degenerate fit (e.g. structural zeros)
        rows.append(dict(call_type=ct, mean_daily=y.mean(), logrr=c, se=se, z=c / se if se > 0 else 0,
                         phi=m.phi))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["rr"] = np.exp(df["logrr"])
    df["rr_lo"] = np.exp(df["logrr"] - 1.96 * df["se"])
    df["rr_hi"] = np.exp(df["logrr"] + 1.96 * df["se"])
    df["p"] = 2 * stats.norm.sf(np.abs(df["z"]))
    order = df["p"].rank(method="first")
    q = (df["p"] * len(df) / order)
    df["q"] = q.sort_values(ascending=False).cummin().reindex(df.index).clip(upper=1)
    return df.sort_values("z", ascending=False).reset_index(drop=True)


def normal_temp(temp, train_end, n_harm=3):
    """Climatological normal for each calendar day: harmonic regression of temp on day of year,
    fitted on days up to train_end only. Returns a Series over temp's index."""
    t = temp.dropna()[:train_end]
    def H(idx):
        ang = 2 * np.pi * idx.dayofyear.values / 365.25
        cols = [np.ones(len(idx))]
        for k in range(1, n_harm + 1):
            cols += [np.sin(k * ang), np.cos(k * ang)]
        return np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(H(t.index), t.values, rcond=None)
    idx = pd.date_range(temp.index.min(), temp.index.max())
    return pd.Series(H(idx) @ beta, index=idx, name="tnorm")


def surveil(y, temp, start, end, T0, train_years=3, refit_every=7, alpha=0.005, exclude=None,
            temp_ref=None):
    """
    Prospective surveillance. For each block of `refit_every` days from start to end,
    fit the prosp model on the previous `train_years` years only, then score the block.

    Columns: obs, mu_base (heat terms zeroed), mu_full (expectation given observed
    temperature), mu_norm (expectation if the temperature were the climatological normal
    for the date; needs temp_ref), u_* (NB upper limits), heat_expected (= mu_full - mu_base).

    Alarms:
      alarm_norm        obs > u_norm: more calls than this date sees at normal temperature.
                        This is the surveillance alarm (requires temp_ref).
      alarm_unexplained obs > u_full: more calls than even the heat model expects.
      alarm_excess      obs > u_base: kept for reference only. With a low T0 the heat-zeroed
                        baseline sits far below ordinary summer counts, so it fires all summer.
    """
    out = []
    d, end = pd.Timestamp(start), pd.Timestamp(end)
    while d <= end:
        hist = y[d - pd.DateOffset(years=train_years): d - pd.Timedelta(days=1)]
        m = HeatModel("prosp", T0).fit(hist, temp, exclude)
        block = pd.date_range(d, min(d + pd.Timedelta(days=refit_every - 1), end))
        p = m.predict(block, temp)
        if temp_ref is not None:
            p["mu_norm"] = m.predict(block, temp_ref)["mu_full"]
        p["phi"] = m.phi
        out.append(p)
        d += pd.Timedelta(days=refit_every)
    s = pd.concat(out)
    s["obs"] = y.reindex(s.index)
    s["u_base"] = [nb_upper(m_, ph, alpha) for m_, ph in zip(s["mu_base"], s["phi"])]
    s["u_full"] = [nb_upper(m_, ph, alpha) for m_, ph in zip(s["mu_full"], s["phi"])]
    s["alarm_excess"] = s["obs"] > s["u_base"]
    if "mu_norm" in s:
        s["u_norm"] = [nb_upper(m_, ph, alpha) for m_, ph in zip(s["mu_norm"], s["phi"])]
        s["alarm_norm"] = s["obs"] > s["u_norm"]
    s["alarm"] = s["alarm_norm"] if "alarm_norm" in s else s["alarm_excess"]
    s["alarm_unexplained"] = s["obs"] > s["u_full"]
    ref = s["mu_norm"] if "mu_norm" in s else s["mu_base"]
    s["heat_expected"] = s["mu_full"] - ref          # model-predicted excess over normal Tmax
    s["excess_obs"] = s["obs"] - ref                 # observed excess over normal Tmax
    s["heat_attrib_T0"] = s["mu_full"] - s["mu_base"]  # all calls attributable to Tmax above T0
    s["temp"] = temp.reindex(s.index)
    return s


def forecast(y, temp, T0, train_years=3, exclude=None, days=None, temp_ref=None):
    """Expected calls on forecast days. `days`: the dates that are genuine weather forecasts
    (wx['forecast'] == True). Observed weather after the last EMS day is NOT a forecast and is
    ignored. heat_expected = expected calls minus expected at normal Tmax (if temp_ref given)."""
    last = y.index.max()
    fut = pd.DatetimeIndex(days if days is not None else [])
    fut = fut[fut > last]
    if len(fut) == 0:
        return None
    hist = y[last - pd.DateOffset(years=train_years): last]
    m = HeatModel("prosp", T0).fit(hist, temp, exclude)
    p = m.predict(fut, temp)
    ref = m.predict(fut, temp_ref)["mu_full"] if temp_ref is not None else p["mu_base"]
    p["mu_norm"] = ref
    p["heat_expected"] = p["mu_full"] - ref
    p["temp"] = temp.reindex(fut)
    return p


def heat_events(temp, thresh=32.2, min_days=3):
    """NWS/NYC-style heat waves: >= min_days consecutive days with Tmax >= thresh (90F)."""
    hot = (temp >= thresh).astype(int)
    grp = (hot.diff() != 0).cumsum()
    ev = []
    for _, s in hot.groupby(grp):
        if s.iloc[0] == 1 and len(s) >= min_days:
            ev.append(dict(start=s.index[0], end=s.index[-1], days=len(s),
                           peak=float(temp[s.index].max())))
    return pd.DataFrame(ev)


def backtest_events(surv, events, after=3):
    """Per heat wave: first alarm relative to onset, observed excess vs model-expected heat calls."""
    rows = []
    for _, e in events.iterrows():
        win = surv.loc[e["start"]: e["end"] + pd.Timedelta(days=after)]
        if win.empty:
            continue
        acol = "alarm_norm" if "alarm_norm" in win else "alarm_excess"
        alarms = win.index[win[acol]]
        first = alarms.min() if len(alarms) else None
        rows.append(dict(
            start=e["start"].date(), end=e["end"].date(), days=e["days"], peak_tmax=e["peak"],
            alarm_days=int(win[acol].sum()),
            first_alarm=first.date() if first is not None else None,
            days_to_first_alarm=(first - e["start"]).days if first is not None else None,
            obs=float(win["obs"].sum()),
            expected_normal=float(win["mu_norm"].sum() if "mu_norm" in win else win["mu_base"].sum()),
            excess_obs=float(win["excess_obs"].sum()), heat_expected=float(win["heat_expected"].sum()),
            unexplained_days=int(win["alarm_unexplained"].sum()),
        ))
    df = pd.DataFrame(rows)
    if len(df):
        df["days_to_first_alarm"] = df["days_to_first_alarm"].astype("Int64")
    return df


def poisson_ci(o, alpha=0.05):
    lo = np.where(o > 0, stats.chi2.ppf(alpha / 2, 2 * o) / 2, 0.0)
    hi = stats.chi2.ppf(1 - alpha / 2, 2 * (o + 1)) / 2
    return lo, hi


def zip_ratios(zip_daily, types, surv, event, temp, T0=None, after=3, min_ref=20, ref_max=29.4):
    """
    Indirectly standardised ratio per zip for one heat wave.
      share_z   = zip's share of the outcome on reference days (Jun-Sep of the event year
                  and the year before, Tmax < ref_max (29.4 C = 85 F), outside the heat wave window)
      E_z       = share_z * sum(mu_base over window)     -> SIR_z = O_z / E_z
      relative  = SIR_z / citywide SIR   (> 1: zip hit harder than the city as a whole)
    """
    z = zip_daily[zip_daily["call_type"].isin(types)].groupby(["date", "zipcode"])["n"].sum().unstack(fill_value=0)
    s, e = pd.Timestamp(event["start"]), pd.Timestamp(event["end"]) + pd.Timedelta(days=after)
    yr = s.year
    ref_days = z.index[z.index.year.isin([yr - 1, yr]) & z.index.month.isin([6, 7, 8, 9])]
    ref_days = ref_days[(temp.reindex(ref_days) < ref_max).values]
    ref_days = ref_days[(ref_days < s - pd.Timedelta(days=3)) | (ref_days > e)]
    ref = z.loc[ref_days].sum()
    ref = ref[ref.index != "UNKNOWN"]
    share = ref / ref.sum()
    win = z.loc[s:e].sum().reindex(share.index, fill_value=0)
    E_city = surv.loc[s:e, "mu_norm" if "mu_norm" in surv else "mu_base"].sum()
    O_city = surv.loc[s:e, "obs"].sum()
    E = share * E_city
    out = pd.DataFrame({"obs": win, "expected": E, "ref_calls": ref})
    out = out[out["ref_calls"] >= min_ref]
    out["sir"] = out["obs"] / out["expected"]
    lo, hi = poisson_ci(out["obs"].values)
    out["sir_lo"], out["sir_hi"] = lo / out["expected"], hi / out["expected"]
    out["relative"] = out["sir"] / (O_city / E_city)
    return out.sort_values("sir", ascending=False)


def pool_zip_ratios(zrs):
    """Pool several heat waves: sum observed and expected per zip."""
    if not zrs:
        return None
    a = pd.concat(zrs.values())
    g = a.groupby(level=0)[["obs", "expected"]].sum()
    g = g[g.index.isin(set.intersection(*[set(z.index) for z in zrs.values()]))]
    g["sir"] = g["obs"] / g["expected"]
    lo, hi = poisson_ci(g["obs"].values)
    g["sir_lo"], g["sir_hi"] = lo / g["expected"], hi / g["expected"]
    g["relative"] = g["sir"] / (g["obs"].sum() / g["expected"].sum())
    g.index.name = "zipcode"
    return g.sort_values("relative", ascending=False)
