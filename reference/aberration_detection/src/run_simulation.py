"""
Simulation study: compare detectors across disease profiles and outbreak sizes.

Usage:
    python src/run_simulation.py --n-sims 30 --k 2 4 6 8 --out results/
"""
import argparse
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulate import PROFILES, simulate_series
from detectors import DETECTORS
from evaluate import score

COLORS = {
    "EARS C1": "#9ecae1", "EARS C2": "#4292c6", "EARS C3": "#08519c",
    "Farrington Flexible": "#d95f0e", "Harmonic GLM": "#31a354",
}


def _one(args):
    pname, k, sim = args
    seed = zlib.crc32(f"{pname}-{k}-{sim}".encode())
    df, obs, eval_idx = simulate_series(PROFILES[pname], k, seed=seed)
    y = df["count"].to_numpy()
    return [dict(profile=pname, k=k, sim=sim, detector=dname, **score(det(y, eval_idx), df, obs))
            for dname, det in DETECTORS.items()]


def run(n_sims, ks, out_dir, workers=None):
    jobs = [(p, k, s) for p in PROFILES for k in ks for s in range(n_sims)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = [r for batch in ex.map(_one, jobs, chunksize=4) for r in batch]
    print(f"{len(jobs)} simulated series in {time.time() - t0:.0f}s")
    res = pd.DataFrame(rows)
    res.to_csv(out_dir / "sim_results_raw.csv", index=False)
    return res


def summarise(res, out_dir):
    summ = (res.groupby(["profile", "k", "detector"])
               .agg(fpr=("fpr", "mean"), pod=("pod", "mean"),
                    sensitivity=("sensitivity", "mean"), mean_lag=("mean_lag", "mean"))
               .reset_index())
    summ.to_csv(out_dir / "sim_summary.csv", index=False)
    fpr = (res.groupby(["profile", "detector"])["fpr"].mean()
              .unstack("profile").round(3))
    fpr.to_csv(out_dir / "fpr_by_profile.csv")
    return summ, fpr


def plot_pod(summ, out_dir):
    profiles = list(PROFILES)
    fig, axes = plt.subplots(1, len(profiles), figsize=(4.2 * len(profiles), 3.8), sharey=True)
    for ax, p in zip(axes, profiles):
        s = summ[summ["profile"] == p]
        for dname, g in s.groupby("detector"):
            ax.plot(g["k"], g["pod"], marker="o", label=dname, color=COLORS[dname])
        ax.set_title(p.replace("_", " "))
        ax.set_xlabel("Outbreak size (k × baseline SD)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Probability of detection")
    axes[0].set_ylim(0, 1.02)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out_dir / "pod_vs_outbreak_size.png", dpi=150)
    plt.close(fig)


def plot_tradeoff(summ, out_dir, k_show=4):
    profiles = list(PROFILES)
    fig, axes = plt.subplots(1, len(profiles), figsize=(4.2 * len(profiles), 3.8))
    for ax, p in zip(axes, profiles):
        s = summ[(summ["profile"] == p) & (summ["k"] == k_show)]
        for r in s.itertuples():
            ax.scatter(r.fpr, r.pod, s=70, color=COLORS[r.detector], label=r.detector)
        ax.set_title(f"{p.replace('_', ' ')} (k={k_show})")
        ax.set_xlabel("False positive rate (per week)")
        ax.set_xlim(0, max(0.05, s["fpr"].max() * 1.15))
        ax.set_ylim(0, 1.02)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Probability of detection")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out_dir / "pod_fpr_tradeoff.png", dpi=150)
    plt.close(fig)


def plot_example(out_dir, profile="medium_seasonal", k=5, seed=11):
    df, obs, eval_idx = simulate_series(PROFILES[profile], k, seed=seed)
    y = df["count"].to_numpy()
    show = ["EARS C2", "Farrington Flexible", "Harmonic GLM"]
    fig, axes = plt.subplots(len(show), 1, figsize=(11, 2.6 * len(show)), sharex=True)
    ev = df[df["week"].isin(eval_idx)]
    for ax, dname in zip(axes, show):
        out = DETECTORS[dname](y, eval_idx)
        ax.bar(ev["week"], ev["baseline"], color="#bdbdbd", width=1.0, label="Baseline cases")
        ax.bar(ev["week"], ev["outbreak_cases"], bottom=ev["baseline"], color="#fdae6b",
               width=1.0, label="Injected outbreak cases")
        ax.step(out["week"], out["threshold"], where="mid", color=COLORS[dname], lw=1.5, label="Threshold")
        a = out[out["alarm"]]
        ax.scatter(a["week"], a["observed"] + 1.5, marker="v", color="red", s=30, zorder=5, label="Alarm")
        ax.set_title(dname, loc="left", fontsize=10)
        ax.set_ylabel("Weekly cases")
    axes[0].legend(fontsize=8, ncol=4, loc="upper left")
    axes[-1].set_xlabel("Week")
    fig.tight_layout()
    fig.savefig(out_dir / "example_series.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sims", type=int, default=30)
    ap.add_argument("--k", type=float, nargs="+", default=[2, 4, 6, 8])
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    res = run(a.n_sims, a.k, a.out)
    summ, fpr = summarise(res, a.out)
    plot_pod(summ, a.out)
    plot_tradeoff(summ, a.out, k_show=int(a.k[len(a.k) // 2]))
    plot_example(a.out)
    print("\nMean weekly FPR by profile:\n", fpr)
    print("\nPOD at each k:\n",
          summ.pivot_table(index=["profile", "detector"], columns="k", values="pod").round(2))
