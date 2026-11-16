"""
Aberration detection algorithms for weekly count surveillance data.

Every detector has the signature  detector(y, eval_idx, **params) -> DataFrame
with columns: week, observed, expected, threshold, alarm.
Each week is scored using only data available before it (prospective use).

Implemented
-----------
- EARS C1, C2, C3            Hutwagner et al. 2003 (CDC EARS)
- Farrington Flexible         Noufaily et al. 2013 (as in R `surveillance::farringtonFlexible`)
- Harmonic quasi-Poisson      Serfling-type rolling regression with Fourier seasonality

The GLM is fitted with a small numpy IRLS so the prototype depends only on
numpy/scipy. Results should be cross-checked against R `surveillance` before
publication (see README).
"""
import numpy as np
import pandas as pd
from scipy import stats

WEEKS_PER_YEAR = 52


# --------------------------------------------------------------------------- #
# EARS
# --------------------------------------------------------------------------- #
def _ears_stat(y, t, lag, window, min_sigma):
    ref = y[t - lag - window + 1: t - lag + 1]
    m, s = ref.mean(), max(ref.std(ddof=1), min_sigma)
    return m, s, (y[t] - m) / s


def ears(y, eval_idx, method="C1", min_sigma=0.5, z=3.0, c3_threshold=2.0):
    """
    C1: 7-week baseline immediately before t.
    C2: 7-week baseline with a 2-week guard (t-9 .. t-3).
    C3: sum of max(0, C2_stat - 1) over t-2 .. t; alarm if > 2.
    min_sigma floors the SD so an all-zero baseline doesn't alarm on 1 case.
    """
    y = np.asarray(y, float)
    out = []
    for t in eval_idx:
        if method == "C1":
            m, s, stat = _ears_stat(y, t, lag=1, window=7, min_sigma=min_sigma)
            thr = m + z * s
            alarm = stat > z
        elif method == "C2":
            m, s, stat = _ears_stat(y, t, lag=3, window=7, min_sigma=min_sigma)
            thr = m + z * s
            alarm = stat > z
        elif method == "C3":
            terms = [max(0.0, _ears_stat(y, t - i, 3, 7, min_sigma)[2] - 1) for i in range(3)]
            m, s, _ = _ears_stat(y, t, 3, 7, min_sigma)
            prev = terms[1] + terms[2]
            # count at t needed to push C3 above threshold, given the two prior terms
            thr = m + s * (1 + max(0.0, c3_threshold - prev))
            alarm = sum(terms) > c3_threshold
        else:
            raise ValueError(method)
        out.append((t, y[t], m, thr, alarm))
    return pd.DataFrame(out, columns=["week", "observed", "expected", "threshold", "alarm"])


# --------------------------------------------------------------------------- #
# Quasi-Poisson GLM helpers (numpy IRLS)
# --------------------------------------------------------------------------- #
def _poisson_irls(X, y, w, maxit=50, tol=1e-8):
    mu = np.maximum(y, 0.5).astype(float)
    eta = np.log(mu)
    beta = np.zeros(X.shape[1])
    ridge = 1e-8 * np.eye(X.shape[1])
    for _ in range(maxit):
        z = eta + (y - mu) / mu
        W = w * mu
        XtW = X.T * W
        beta_new = np.linalg.solve(XtW @ X + ridge, XtW @ z)
        eta = np.clip(X @ beta_new, -30, 30)
        mu = np.exp(eta)
        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            break
        beta = beta_new
    W = w * mu
    cov_unscaled = np.linalg.inv((X.T * W) @ X + ridge)
    n, p = X.shape
    phi = max(1.0, np.sum(w * (y - mu) ** 2 / mu) / max(n - p, 1))
    hat = W * np.einsum("ij,jk,ik->i", X, cov_unscaled, X)
    return beta, mu, phi, cov_unscaled, hat


def _reweighted_fit(X, y, reweight=True, weight_threshold=2.58):
    """Fit, downweight past outbreaks via Anscombe residuals, refit (Farrington step)."""
    n = len(y)
    w = np.ones(n)
    beta, mu, phi, cov, hat = _poisson_irls(X, y, w)
    if reweight:
        r_ans = 1.5 * (np.cbrt(y) ** 2 - np.cbrt(mu) ** 2) / mu ** (1 / 6)
        s = r_ans / np.sqrt(phi * np.clip(1 - hat, 1e-6, None))
        w = np.where(s > weight_threshold, 1.0 / np.maximum(s, weight_threshold) ** 2, 1.0)
        w *= n / w.sum()
        beta, mu, phi, cov, hat = _poisson_irls(X, y, w)
    return beta, phi, cov


def _nb_upper(mu0, phi, alpha):
    """(1 - alpha) quantile of NB(mean=mu0, var=phi*mu0); Poisson if phi == 1."""
    if mu0 <= 0:
        return 0.0
    if phi <= 1.0 + 1e-9:
        return float(stats.poisson.ppf(1 - alpha, mu0))
    size = mu0 / (phi - 1.0)
    return float(stats.nbinom.ppf(1 - alpha, size, size / (size + mu0)))


def _min_cases_ok(y, t, min_cases_4w):
    return y[max(0, t - 3): t + 1].sum() >= min_cases_4w


# --------------------------------------------------------------------------- #
# Farrington Flexible
# --------------------------------------------------------------------------- #
def _period_factor(ts, t0, w, n_periods):
    """Period 0 = the (2w+1)-week window around t0's calendar week in past years;
    the rest of the cycle is split into n_periods-1 equal blocks."""
    phase = (ts - t0) % WEEKS_PER_YEAR
    in_window = (phase <= w) | (phase >= WEEKS_PER_YEAR - w)
    rest_len = WEEKS_PER_YEAR - 2 * w - 1
    block = 1 + ((phase - (w + 1)) * (n_periods - 1)) // rest_len
    return np.where(in_window, 0, block)


def farrington_flexible(
    y, eval_idx, b=5, w=3, n_periods=10, guard=26, alpha=0.05,
    trend_p=0.05, min_years_for_trend=3, min_cases_4w=5, reweight=True,
):
    """
    Reference data: b years back, excluding the most recent `guard` weeks.
    Model: log mu = a + (beta * t) + seasonal factor (n_periods levels).
    Trend kept only if significant and it doesn't extrapolate above the baseline max.
    Threshold: NB plug-in (1 - alpha) upper quantile. Alarm also requires
    >= min_cases_4w cases in the last 4 weeks.
    """
    y = np.asarray(y, float)
    out = []
    for t0 in eval_idx:
        ts = np.arange(max(0, t0 - b * WEEKS_PER_YEAR - w), t0 - guard + 1)
        yb = y[ts]
        if yb.sum() == 0:
            mu0, phi = 0.0, 1.0
        else:
            per = _period_factor(ts, t0, w, n_periods)
            levels = [p for p in range(1, n_periods) if np.any(per == p)]
            dummies = np.column_stack([(per == p).astype(float) for p in levels]) if levels else np.empty((len(ts), 0))
            tc = (ts - t0) / WEEKS_PER_YEAR  # centred on t0, in years
            x0_season = np.zeros(len(levels))

            use_trend = len(ts) >= min_years_for_trend * WEEKS_PER_YEAR
            mu0 = None
            if use_trend:
                X = np.column_stack([np.ones(len(ts)), tc, dummies])
                beta, phi, cov = _reweighted_fit(X, yb, reweight)
                se = np.sqrt(phi * cov[1, 1])
                p = 2 * (1 - stats.norm.cdf(abs(beta[1] / se)))
                cand = float(np.exp(np.r_[1.0, 0.0, x0_season] @ beta))
                if p < trend_p and cand <= yb.max():
                    mu0 = cand
            if mu0 is None:
                X = np.column_stack([np.ones(len(ts)), dummies])
                beta, phi, cov = _reweighted_fit(X, yb, reweight)
                mu0 = float(np.exp(np.r_[1.0, x0_season] @ beta))
        thr = _nb_upper(mu0, phi, alpha)
        alarm = (y[t0] > thr) and _min_cases_ok(y, t0, min_cases_4w)
        out.append((t0, y[t0], mu0, thr, alarm))
    return pd.DataFrame(out, columns=["week", "observed", "expected", "threshold", "alarm"])


# --------------------------------------------------------------------------- #
# Harmonic (Serfling-type) quasi-Poisson regression
# --------------------------------------------------------------------------- #
def harmonic_glm(y, eval_idx, years=3, guard=8, harmonics=2, alpha=0.05,
                 reweight=True, min_cases_4w=5):
    """
    Rolling quasi-Poisson regression on the last `years` of data (minus a guard),
    with linear trend and Fourier terms. Uses every week, so it borrows more
    information than Farrington's seasonal blocks but is more sensitive to
    model misspecification of the seasonal shape.
    """
    y = np.asarray(y, float)
    out = []
    for t0 in eval_idx:
        ts = np.arange(max(0, t0 - years * WEEKS_PER_YEAR), t0 - guard + 1)
        yb = y[ts]

        def design(t):
            t = np.atleast_1d(t).astype(float)
            cols = [np.ones_like(t), (t - t0) / WEEKS_PER_YEAR]
            for j in range(1, harmonics + 1):
                ang = 2 * np.pi * j * t / WEEKS_PER_YEAR
                cols += [np.cos(ang), np.sin(ang)]
            return np.column_stack(cols)

        if yb.sum() == 0:
            mu0, phi = 0.0, 1.0
        else:
            beta, phi, _ = _reweighted_fit(design(ts), yb, reweight)
            mu0 = float(np.exp(design(t0) @ beta)[0])
        thr = _nb_upper(mu0, phi, alpha)
        alarm = (y[t0] > thr) and _min_cases_ok(y, t0, min_cases_4w)
        out.append((t0, y[t0], mu0, thr, alarm))
    return pd.DataFrame(out, columns=["week", "observed", "expected", "threshold", "alarm"])


DETECTORS = {
    "EARS C1": lambda y, idx: ears(y, idx, "C1"),
    "EARS C2": lambda y, idx: ears(y, idx, "C2"),
    "EARS C3": lambda y, idx: ears(y, idx, "C3"),
    "Farrington Flexible": farrington_flexible,
    "Harmonic GLM": harmonic_glm,
}
