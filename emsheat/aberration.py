"""
Generic aberration detectors for daily counts, ported from reference/aberration_detection
(weekly notifiable-disease version) to daily EMS series.

All detectors are prospective: day t is scored using only data before t.
Each returns a DataFrame indexed by date: obs, expected, threshold, alarm.

  EARS C1   baseline t-7..t-1,  alarm if (y - mean)/sd > 3
  EARS C2   baseline t-9..t-3 (2-day guard), same rule
  EARS C3   sum over t-2..t of max(0, C2 stat - 1) > 2
            (C1-C3 were designed for daily syndromic data, so these are the original forms)
  Farrington Flexible (Noufaily et al. 2013), daily adaptation:
            reference = the previous b years, minus a guard of the most recent `guard` days;
            seasonality = a factor with n_periods levels: level 0 is the window of +/- w days
            around t's day of year in each past year, the rest of the year is split into
            n_periods-1 blocks; optional linear trend kept only if significant and it does not
            extrapolate above the reference max; past outbreaks downweighted via Anscombe
            residuals > 2.58; alarm if y > NB (1-alpha) quantile of the plug-in prediction and
            >= min_cases in the last 28 days.
            No day-of-week term (faithful to Farrington), which matters for high-volume series.

Unlike the heat model (emsheat.model.surveil), none of these uses temperature.
The GLM is a small numpy IRLS (same as the reference project); not yet cross-checked
against R surveillance::farringtonFlexible on these series.
"""
import numpy as np
import pandas as pd
from scipy import stats

DPY = 365.25


# --------------------------------------------------------------------------- #
# EARS
# --------------------------------------------------------------------------- #
def _ears_stat(y, t, lag, window, min_sigma):
    ref = y[t - lag - window + 1: t - lag + 1]
    m, s = ref.mean(), max(ref.std(ddof=1), min_sigma)
    return m, s, (y[t] - m) / s


def ears(series, start, end, method="C1", min_sigma=0.5, z=3.0, c3_threshold=2.0):
    s = series.astype(float)
    y = s.values
    idx = np.where((s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end)))[0]
    out = []
    for t in idx:
        if t < 12:
            continue
        if method == "C1":
            m, sd, st = _ears_stat(y, t, 1, 7, min_sigma)
            thr, alarm = m + z * sd, st > z
        elif method == "C2":
            m, sd, st = _ears_stat(y, t, 3, 7, min_sigma)
            thr, alarm = m + z * sd, st > z
        elif method == "C3":
            terms = [max(0.0, _ears_stat(y, t - i, 3, 7, min_sigma)[2] - 1) for i in range(3)]
            m, sd, _ = _ears_stat(y, t, 3, 7, min_sigma)
            thr = m + sd * (1 + max(0.0, c3_threshold - terms[1] - terms[2]))
            alarm = sum(terms) > c3_threshold
        else:
            raise ValueError(method)
        out.append((s.index[t], y[t], m, thr, bool(alarm)))
    return pd.DataFrame(out, columns=["date", "obs", "expected", "threshold", "alarm"]).set_index("date")


# --------------------------------------------------------------------------- #
# Quasi-Poisson IRLS with case weights (from the reference project)
# --------------------------------------------------------------------------- #
def _poisson_irls(X, y, w, maxit=50, tol=1e-8):
    mu = np.maximum(y, 0.5).astype(float)
    eta = np.log(mu)
    beta = np.zeros(X.shape[1])
    ridge = 1e-8 * np.eye(X.shape[1])
    for _ in range(maxit):
        zz = eta + (y - mu) / mu
        W = w * mu
        XtW = X.T * W
        beta_new = np.linalg.solve(XtW @ X + ridge, XtW @ zz)
        eta = np.clip(X @ beta_new, -30, 30)
        mu = np.exp(eta)
        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            break
        beta = beta_new
    W = w * mu
    cov = np.linalg.inv((X.T * W) @ X + ridge)
    n, p = X.shape
    phi = max(1.0, np.sum(w * (y - mu) ** 2 / mu) / max((w > 0).sum() - p, 1))
    hat = W * np.einsum("ij,jk,ik->i", X, cov, X)
    return beta, mu, phi, cov, hat


def _reweighted_fit(X, y, base_w, reweight=True, thr=2.58):
    beta, mu, phi, cov, hat = _poisson_irls(X, y, base_w)
    if reweight:
        r = 1.5 * (np.cbrt(y) ** 2 - np.cbrt(mu) ** 2) / mu ** (1 / 6)
        s = r / np.sqrt(phi * np.clip(1 - hat, 1e-6, None))
        w = np.where(s > thr, 1.0 / np.maximum(s, thr) ** 2, 1.0) * base_w
        w *= base_w.sum() / max(w.sum(), 1e-9)
        beta, mu, phi, cov, hat = _poisson_irls(X, y, w)
    return beta, phi, cov


def _nb_upper(mu0, phi, alpha):
    if mu0 <= 0:
        return 0.0
    if phi <= 1.0 + 1e-9:
        return float(stats.poisson.ppf(1 - alpha, mu0))
    size = mu0 / (phi - 1.0)
    return float(stats.nbinom.ppf(1 - alpha, size, size / (size + mu0)))


# --------------------------------------------------------------------------- #
# Farrington Flexible, daily
# --------------------------------------------------------------------------- #
def farrington_flexible(series, start, end, b=5, w=7, n_periods=10, guard=182, alpha=0.005,
                        trend_p=0.05, min_years_for_trend=3, min_cases=5, reweight=True,
                        exclude=None):
    s = series.astype(float)
    y = s.values
    dates = s.index
    doy = dates.dayofyear.values
    base_w = np.ones(len(y))
    for a, e in exclude or []:
        base_w[(dates >= pd.Timestamp(a)) & (dates <= pd.Timestamp(e))] = 0.0
    idx = np.where((dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end)))[0]
    span = int(round(b * DPY))
    out = []
    for t0 in idx:
        ts = np.arange(max(0, t0 - span - w), t0 - guard + 1)
        yb, wb = y[ts], base_w[ts]
        keep = wb > 0
        ts, yb, wb = ts[keep], yb[keep], wb[keep]
        if len(ts) < DPY or yb.sum() == 0:
            mu0, phi = (0.0, 1.0) if len(ts) >= DPY else (np.nan, 1.0)
        else:
            # circular day-of-year distance from t0
            ph = (doy[ts] - doy[t0]) % 365
            in_win = (ph <= w) | (ph >= 365 - w)
            rest = 365 - 2 * w - 1
            per = np.where(in_win, 0, 1 + ((ph - (w + 1)) * (n_periods - 1)) // rest)
            levels = [p for p in range(1, n_periods) if np.any(per == p)]
            D = np.column_stack([(per == p).astype(float) for p in levels]) if levels else np.empty((len(ts), 0))
            tc = (ts - t0) / DPY
            mu0 = None
            if (ts.max() - ts.min()) >= min_years_for_trend * DPY:
                X = np.column_stack([np.ones(len(ts)), tc, D])
                beta, phi, cov = _reweighted_fit(X, yb, wb, reweight)
                se = np.sqrt(phi * cov[1, 1])
                p = 2 * (1 - stats.norm.cdf(abs(beta[1] / se)))
                cand = float(np.exp(beta[0]))
                if p < trend_p and cand <= yb.max():
                    mu0 = cand
            if mu0 is None:
                X = np.column_stack([np.ones(len(ts)), D])
                beta, phi, cov = _reweighted_fit(X, yb, wb, reweight)
                mu0 = float(np.exp(beta[0]))
        thr = _nb_upper(mu0, phi, alpha) if np.isfinite(mu0) else np.nan
        recent = y[max(0, t0 - 27): t0 + 1].sum()
        alarm = bool(np.isfinite(thr) and y[t0] > thr and recent >= min_cases)
        out.append((dates[t0], y[t0], mu0, thr, alarm))
    return pd.DataFrame(out, columns=["date", "obs", "expected", "threshold", "alarm"]).set_index("date")


def run_all(series, start, end, alpha=0.005, exclude=None):
    """All generic detectors on one series. Returns {name: DataFrame}."""
    return {
        "EARS C1": ears(series, start, end, "C1"),
        "EARS C2": ears(series, start, end, "C2"),
        "EARS C3": ears(series, start, end, "C3"),
        "Farrington Flexible": farrington_flexible(series, start, end, alpha=alpha, exclude=exclude),
    }
