"""
Simulate weekly notifiable-disease counts with injected outbreaks.

Follows the design in Noufaily et al. (2013, Stat Med 32:1206-1222):
baseline counts are negative binomial with log-linear trend and Fourier
seasonality; outbreak size scales with the baseline SD at the start week,
and outbreak cases are spread over subsequent weeks with a lognormal delay.
Ground truth (which weeks carry outbreak cases, per outbreak) is returned
so detectors can be scored.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd

WEEKS_PER_YEAR = 52


@dataclass(frozen=True)
class Profile:
    name: str
    theta: float    # log baseline level
    beta: float     # linear trend per week (log scale)
    gamma1: float   # cosine amplitude
    gamma2: float   # sine amplitude
    m: int          # number of harmonics
    phi: float      # dispersion (variance = phi * mu); 1 = Poisson


PROFILES = {
    # ~2 cases/wk, weak seasonality, Poisson: sparse rare-disease regime
    "low_sparse": Profile("low_sparse", 0.5, 0.0, 0.2, 0.2, 1, 1.0),
    # ~12 cases/wk, clear annual cycle, overdispersed: e.g. salmonellosis at state level
    "medium_seasonal": Profile("medium_seasonal", 2.5, 0.0, 0.6, 0.6, 1, 1.5),
    # ~30-230 cases/wk, rising trend, two harmonics, overdispersed: e.g. campylobacteriosis nationally
    "high_trend": Profile("high_trend", 4.0, 0.0015, 0.4, 0.2, 2, 2.0),
}


def baseline_mean(profile: Profile, n_weeks: int) -> np.ndarray:
    t = np.arange(n_weeks)
    log_mu = profile.theta + profile.beta * t
    for j in range(1, profile.m + 1):
        ang = 2 * np.pi * j * t / WEEKS_PER_YEAR
        log_mu += profile.gamma1 * np.cos(ang) + profile.gamma2 * np.sin(ang)
    return np.exp(log_mu)


def draw_counts(mu: np.ndarray, phi: float, rng: np.random.Generator) -> np.ndarray:
    if phi <= 1.0:
        return rng.poisson(mu)
    size = mu / (phi - 1.0)
    return rng.negative_binomial(size, size / (size + mu))


def _pick_starts(rng, lo, hi, n, min_gap):
    """n outbreak start weeks in [lo, hi), at least min_gap apart."""
    for _ in range(1000):
        s = np.sort(rng.choice(np.arange(lo, hi), size=n, replace=False))
        if n == 1 or np.all(np.diff(s) >= min_gap):
            return s
    raise RuntimeError("Could not place non-overlapping outbreaks")


def simulate_series(
    profile: Profile,
    k: float,
    n_years: int = 8,
    eval_years: int = 2,
    n_baseline_outbreaks: int = 4,
    n_eval_outbreaks: int = 3,
    seed: int | None = None,
):
    """
    Returns
    -------
    df : DataFrame with week, mu, baseline, outbreak_cases, count, outbreak_id
    outbreaks : DataFrame with outbreak_id, start, end, size, in_eval
    eval_idx : ndarray of week indices in the evaluation period
    """
    rng = np.random.default_rng(seed)
    T = n_years * WEEKS_PER_YEAR
    eval_start = T - eval_years * WEEKS_PER_YEAR

    mu = baseline_mean(profile, T)
    base = draw_counts(mu, profile.phi, rng)

    # Outbreaks in baseline years contaminate the reference data (tests robustness);
    # outbreaks in the evaluation period are the ones we score.
    starts_base = _pick_starts(rng, 0, eval_start - 10, n_baseline_outbreaks, 12)
    starts_eval = _pick_starts(rng, eval_start, T - 6, n_eval_outbreaks, 12)

    ob_cases = np.zeros(T, dtype=int)
    ob_id = np.full(T, -1)
    rows = []
    for i, s in enumerate(np.concatenate([starts_base, starts_eval])):
        sd = np.sqrt(profile.phi * mu[s])
        size = rng.poisson(k * sd)
        if size == 0:
            continue
        delays = np.floor(rng.lognormal(0.0, 0.5, size)).astype(int)
        weeks = s + delays
        weeks = weeks[weeks < T]
        np.add.at(ob_cases, weeks, 1)
        ob_id[weeks] = i
        rows.append(dict(outbreak_id=i, start=int(s), end=int(weeks.max()),
                         size=int(len(weeks)), in_eval=bool(s >= eval_start)))

    df = pd.DataFrame(dict(
        week=np.arange(T), mu=mu, baseline=base,
        outbreak_cases=ob_cases, count=base + ob_cases, outbreak_id=ob_id,
    ))
    return df, pd.DataFrame(rows), np.arange(eval_start, T)
