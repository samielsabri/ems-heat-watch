"""Single-file HTML report (figures embedded) plus a plain-text summary."""
import base64
import html
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

INK, MUTED, GRID = "#1f2328", "#6b7280", "#e5e7eb"
OBS, BASE, HEATC, ALARM, WAVE = "#1f2328", "#2563eb", "#d9480f", "#c92a2a", "#fff1e6"

plt.rcParams.update({
    "font.size": 9.5, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "legend.frameon": False, "figure.dpi": 110,
})


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _shade_waves(ax, events, lo, hi):
    for _, e in events.iterrows():
        if e["end"] >= lo and e["start"] <= hi:
            ax.axvspan(e["start"] - pd.Timedelta(hours=12), e["end"] + pd.Timedelta(hours=12),
                       color=WAVE, zorder=0, lw=0)


def fig_operational(ctx, name, days=60):
    r = ctx["results"][name]
    s = r["surv"].iloc[-days:]
    fc = r["forecast"]
    temp = ctx["temp"]
    fig, (ax, axt) = plt.subplots(2, 1, figsize=(8.6, 4.6), sharex=True, gridspec_kw={"height_ratios": [3, 1.2]})
    lo, hi = s.index.min(), (fc.index.max() if fc is not None and len(fc) else s.index.max())
    _shade_waves(ax, ctx["events"], lo, hi)
    _shade_waves(axt, ctx["events"], lo, hi)
    ref, uref = ("mu_norm", "u_norm") if "mu_norm" in s else ("mu_base", "u_base")
    ax.fill_between(s.index, s[ref], s[uref], color=BASE, alpha=0.10, lw=0, step="mid",
                    label=f"expected at normal Tmax to alarm threshold")
    ax.plot(s.index, s[ref], color=BASE, lw=1.2, label="expected at normal Tmax for the date")
    ax.plot(s.index, s["mu_full"], color=HEATC, lw=1.1, ls="--", label="expected given temperature")
    ax.plot(s.index, s["obs"], color=OBS, lw=1.3, marker="o", ms=2.4, label="observed")
    al = s[s["alarm"]]
    ax.scatter(al.index, al["obs"], s=42, facecolor="none", edgecolor=ALARM, lw=1.4, zorder=5, label="alarm")
    if fc is not None and len(fc):
        ax.plot(fc.index, fc["mu_full"], color=HEATC, lw=1.4, ls="--")
        ax.axvline(ctx["last"] + pd.Timedelta(hours=12), color=MUTED, lw=0.8)
        ax.text(ctx["last"] + pd.Timedelta(hours=18), ax.get_ylim()[1] * 0.97, "forecast", color=MUTED,
                va="top", fontsize=8.5)
    ax.set_title(f"{name}: last {days} days and 7-day outlook")
    ax.set_ylabel("calls per day")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    tt = temp[lo:hi]
    isfc = tt.index > ctx["last"]
    axt.plot(tt.index[~isfc], tt[~isfc], color=HEATC, lw=1.2)
    axt.plot(tt.index[isfc], tt[isfc], color=HEATC, lw=1.2, ls=":")
    axt.axhline(r["T0"], color=MUTED, lw=0.8, ls="--")
    axt.text(lo, r["T0"] + 0.4, f"T0 {r['T0']:.1f} °C", color=MUTED, fontsize=8)
    axt.set_ylabel("Tmax °C")
    axt.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.tight_layout()
    return _png(fig)


def fig_timeline(ctx, name):
    r = ctx["results"][name]
    s = r["surv"]
    fig, ax = plt.subplots(figsize=(8.6, 2.9))
    _shade_waves(ax, ctx["events"], s.index.min(), s.index.max())
    ax.plot(s.index, s["obs"], color=OBS, lw=0.7, label="observed")
    ref = "mu_norm" if "mu_norm" in s else "mu_base"
    ax.plot(s.index, s[ref], color=BASE, lw=1.1, label="expected at normal Tmax")
    al = s[s["alarm"]]
    ax.scatter(al.index, al["obs"], s=16, color=ALARM, zorder=5, label="alarm")
    ax.set_title(f"{name}: prospective surveillance over the evaluation period (heat waves shaded)")
    ax.set_ylabel("calls per day")
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.tight_layout()
    return _png(fig)


def fig_curves(ctx):
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    temps = np.linspace(20, 38, 100)
    cols = ["#d9480f", "#7048e8", "#1f2328", "#2b8a3e"]
    for (name, r), c in zip(ctx["results"].items(), cols):
        cv = r["retro"].curve(temps)
        ax.plot(cv["temp"], cv["rr"], color=c, lw=1.6, label=name)
        ax.fill_between(cv["temp"], cv["lo"], cv["hi"], color=c, alpha=0.12, lw=0)
    ax.set_yscale("log")
    ax.axhline(1, color=MUTED, lw=0.8)
    ax.set_xlabel("sustained daily Tmax, °C")
    ax.set_ylabel("rate ratio (log scale)")
    ax.set_title("Exposure-response (training period)")
    ax.legend(fontsize=7.5, loc="upper left")
    fig.tight_layout()
    return _png(fig)


def fig_screen(ctx, top=16):
    s = ctx["screen"].head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(5.4, 0.26 * len(s) + 1.0))
    y = np.arange(len(s))
    sig = (s["q"] < 0.05) & (s["rr"] > 1)
    ax.errorbar((s["rr"] - 1) * 100, y, xerr=[(s["rr"] - s["rr_lo"]) * 100, (s["rr_hi"] - s["rr"]) * 100],
                fmt="none", ecolor=GRID, elinewidth=2)
    ax.scatter((s["rr"] - 1) * 100, y, c=np.where(sig, HEATC, MUTED), s=22, zorder=3)
    ax.set_yticks(y, s["call_type"])
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_xlabel(f"% change in calls per °C above {ctx['T0']:.1f} °C")
    ax.set_title("Call types ranked by heat sensitivity")
    ax.set_xscale("symlog", linthresh=10)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return _png(fig)


def fig_zips(zr, title, top=15):
    s = zr.head(top).iloc[::-1]
    s = s.assign(sir=s["relative"], sir_lo=s["sir_lo"] * s["relative"] / s["sir"], sir_hi=s["sir_hi"] * s["relative"] / s["sir"])
    fig, ax = plt.subplots(figsize=(5.4, 0.26 * len(s) + 1.0))
    y = np.arange(len(s))
    ax.errorbar(s["sir"], y, xerr=[s["sir"] - s["sir_lo"], s["sir_hi"] - s["sir"]], fmt="none",
                ecolor=GRID, elinewidth=2)
    ax.scatter(s["sir"], y, color=HEATC, s=22, zorder=3)
    ax.set_yticks(y, s.index)
    ax.axvline(1, color=MUTED, lw=0.8)
    ax.set_xlabel("relative ratio (zip vs city, 95% CI)")
    ax.set_title(title)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return _png(fig)


def _table(df, fmt=None):
    fmt = fmt or {}
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            if c in fmt and pd.notna(v):
                v = fmt[c].format(v)
            elif v is None or (isinstance(v, float) and np.isnan(v)):
                v = "–"
            cells.append(f"<td>{html.escape(str(v))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<div class='tw'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


CSS = """
:root{--bg:#fbfaf8;--fg:#1f2328;--muted:#6b7280;--line:#e7e3dc;--card:#ffffff;--accent:#d9480f;--alarm:#c92a2a}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#16171a;--fg:#e8e6e3;--muted:#9aa0a6;--line:#2c2e33;--card:#1d1f23;--accent:#ff8a4c;--alarm:#ff6b6b;color-scheme:dark}}
:root[data-theme=dark]{--bg:#16171a;--fg:#e8e6e3;--muted:#9aa0a6;--line:#2c2e33;--card:#1d1f23;--accent:#ff8a4c;--alarm:#ff6b6b;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:14px/1.55 "IBM Plex Sans",system-ui,sans-serif;margin:0}
main{max-width:960px;margin:0 auto;padding-block:28px 60px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:22px;margin:0 0 4px} h2{font-size:15px;margin:34px 0 8px;letter-spacing:.01em}
.sub{color:var(--muted);margin:0 0 18px;max-width:70ch}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.kpi b{display:block;font-size:20px;font-variant-numeric:tabular-nums}.kpi span{color:var(--muted);font-size:12px}
.kpi.warn b{color:var(--alarm)}
img{max-width:100%;background:#fff;border-radius:6px;border:1px solid var(--line)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:5px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left} th{color:var(--muted);font-weight:600}
p,li{max-width:75ch} .note{color:var(--muted);font-size:12.5px}
code{font-size:12.5px}
"""


def write(ctx, out):
    out = Path(out)
    R, prim, fresh = ctx["results"], ctx["primary"], ctx["fresh"]
    rp = R[prim]
    s = rp["surv"]
    today = s.iloc[-1]
    fc = rp["forecast"]
    fc_heat = float(fc["heat_expected"].sum()) if fc is not None and len(fc) else 0.0
    fc_peak = fc["temp"].max() if fc is not None and len(fc) else np.nan
    recent_alarms = int(s["alarm"].iloc[-7:].sum())

    kp = [
        ("Data current to", fresh["last_complete"], f"{fresh['lag_days']} day(s) behind {fresh['asof']}", False),
        (f"{prim}, latest day", f"{int(today['obs'])}", f"expected {today.get('mu_norm', today['mu_base']):.1f} at normal Tmax (alarm > {today.get('u_norm', today['u_base']):.0f})",
         bool(today["alarm"])),
        ("Alarm days, last 7", f"{recent_alarms}", "observed above the normal-temperature threshold", recent_alarms > 0),
        ("Forecast heat calls, next 7 days", f"{fc_heat:.0f}", f"peak forecast Tmax {fc_peak:.1f} °C", fc_heat >= 5),
    ]
    kpis = "".join(f"<div class='kpi{' warn' if w else ''}'><span>{html.escape(a)}</span><b>{html.escape(b)}</b>"
                   f"<span>{html.escape(c)}</span></div>" for a, b, c, w in kp)

    eff = pd.DataFrame([dict(outcome=k, mean_per_day=r["mean_daily"], T0=r["T0"],
                             pct_per_degC=(r["rr"] - 1) * 100, lo=(r["rr_lo"] - 1) * 100, hi=(r["rr_hi"] - 1) * 100,
                             overdispersion=r["phi"]) for k, r in R.items()])
    bts = []
    for k, r in R.items():
        b = r["backtest"].copy()
        if len(b):
            b.insert(0, "outcome", k)
            bts.append(b)
    bt = pd.concat(bts) if bts else pd.DataFrame()
    btp, bts_sum = pd.DataFrame(), pd.DataFrame()
    if len(bt):
        btp = bt[bt["outcome"] == prim][["start", "days", "peak_tmax", "alarm_days", "days_to_first_alarm", "obs",
                                         "expected_seasonal", "excess_obs", "heat_expected"]].copy()
        btp["days_to_first_alarm"] = btp["days_to_first_alarm"].astype(object).where(btp["days_to_first_alarm"].notna(), "none")
        btp.columns = ["onset", "days", "peak Tmax °C", "alarm days", "first alarm (day)", "observed",
                       "seasonal expected", "observed excess", "model-predicted heat calls"]
        rows = []
        for k, g in bt.groupby("outcome", sort=False):
            hit = g["days_to_first_alarm"].notna()
            rows.append({"outcome": k, "heat waves alarmed": f"{int(hit.sum())}/{len(g)}",
                         "median first alarm (day)": float(g.loc[hit, "days_to_first_alarm"].median()) if hit.any() else None,
                         "observed excess": g["excess_obs"].sum(), "model-predicted": g["heat_expected"].sum()})
        bts_sum = pd.DataFrame(rows)

    fct = None
    if fc is not None and len(fc):
        fct = fc.reset_index().rename(columns={"index": "date"})
        fct["date"] = fct["date"].dt.strftime("%a %d %b")
        fct = fct[["date", "temp", "mu_base", "mu_full", "heat_expected"]]

    zblock = ""
    if ctx.get("zip_pooled") is not None:
        key = f"{len(ctx['zres'])} evaluated heat waves (pooled)"
        zr = ctx["zip_pooled"]
        zt = zr.head(12).reset_index()
        zblock = (f"<h2>Where: zip codes across {key}</h2>"
                  f"<p class='sub'>Indirectly standardised ratios for heat-coded and heat-sensitive calls pooled ({html.escape(', '.join(ctx['zip_types']))}), since heat-coded calls alone are too sparse per zip. Expected counts use each zip's "
                  f"share on ordinary summer days (that year and the year before), scaled to the citywide seasonal expectation. "
                  f"<code>relative</code> above 1 means the zip was hit harder than the city as a whole.</p>"
                  f"<div class='grid2'><img src='data:image/png;base64,{fig_zips(zr, 'Top zips, all evaluated heat waves')}'>"
                  + _table(zt[["zipcode", "obs", "expected", "sir", "sir_lo", "sir_hi", "relative"]],
                           {"expected": "{:.1f}", "sir": "{:.2f}", "sir_lo": "{:.2f}", "sir_hi": "{:.2f}",
                            "relative": "{:.2f}"}) + "</div>")

    scr = ctx["screen"].head(15)[["call_type", "mean_daily", "rr", "rr_lo", "rr_hi", "q"]].copy()
    for c in ("rr", "rr_lo", "rr_hi"):
        scr[c] = (scr[c] - 1) * 100
    scr = scr.rename(columns={"rr": "%/°C", "rr_lo": "lo", "rr_hi": "hi"})

    body = f"""
<title>EMS Heat Watch</title>
<style>{CSS}</style>
<main>
<h1>EMS Heat Watch</h1>
<p class="sub">Daily heat surveillance from EMS dispatch records. Data {ctx['first'].date()} to {ctx['last'].date()};
models trained to {ctx['train_end'].date()}; prospective evaluation from {ctx['eval_start'].date()}.
Primary outcome: <b>{html.escape(prim)}</b>{' (' + ', '.join(rp['types']) + ')' if rp['types'] and len(rp['types']) < 12 else ''}.</p>
<div class="kpis">{kpis}</div>
<img src="data:image/png;base64,{fig_operational(ctx, prim)}">
<p class="note">Blue: what this date normally sees (trend, season, weekday, holidays; no heat). Orange dashed: what the model expects given
observed or forecast temperature. Circles: alarm days, where observed calls exceed the {100 * (1 - ctx['alpha']):.1f}% upper limit of
the seasonal expectation. Shading: heat waves (3+ days ≥ 32.2 °C).</p>

<h2>Why this beats lagged hospital data</h2>
<p>As of {fresh['asof']}, this pipeline sees data to {fresh['last_complete']} ({fresh['lag_days']} day lag). It covers
{fresh['visible_now']} of {len(ctx['events'])} heat waves in the record. With a six-month lag, only {fresh['visible_with_6mo_lag']} would be visible,
and none from the current season.</p>

<h2>Heat waves in the evaluation period</h2>
<p class="sub">Every heat wave since evaluation began, scored prospectively: each week's model saw only earlier data.</p>
{_table(btp, {"peak Tmax °C": "{:.1f}", "observed": "{:.0f}", "seasonal expected": "{:.0f}", "observed excess": "{:+.0f}", "model-predicted heat calls": "{:.0f}"}) if len(btp) else "<p>No heat waves in the evaluation period.</p>"}
<p class="note">{html.escape(prim)}. First alarm counts from heat wave onset (0 = alarm on day one). Observed excess is observed minus
seasonal expectation over the wave plus three days; model-predicted heat calls is what the temperature model expected for the same window.</p>
<h2>All outcomes</h2>
{_table(bts_sum, {"median first alarm (day)": "{:.0f}", "observed excess": "{:+.0f}", "model-predicted": "{:.0f}"}) if len(bts_sum) else ""}
<p class="note">Broader outcomes dilute the heat signal: all-call volume rises in every heat wave but crosses the alarm threshold less often.</p>

<img src="data:image/png;base64,{fig_timeline(ctx, prim)}">

<h2>Heat effect by outcome</h2>
<div class="grid2"><img src="data:image/png;base64,{fig_curves(ctx)}">
{_table(eff, {"mean_per_day": "{:.1f}", "T0": "{:.1f}", "pct_per_degC": "{:+.1f}", "lo": "{:+.1f}", "hi": "{:+.1f}", "overdispersion": "{:.2f}"})}</div>
<p class="note">Cumulative change in daily calls per °C of sustained Tmax above threshold T0 (lags 0–3), from a quasi-Poisson time-series
model with a natural spline of time, day of week and holidays. Fitted on the training period only.</p>

<h2>Which call types respond to heat</h2>
<div class="grid2"><img src="data:image/png;base64,{fig_screen(ctx)}">
{_table(scr, {"mean_daily": "{:.1f}", "%/°C": "{:+.1f}", "lo": "{:+.1f}", "hi": "{:+.1f}", "q": "{:.3g}"})}</div>
<p class="note">Exploratory. Each final call type used throughout the training years (code variants merged) with ≥1 call/day was
screened on the training period; listed as heat-sensitive if FDR q &lt; 0.05 and ≥ +2%/°C. The surveillance syndrome is NOT taken
from this screen: it is pre-specified (emsheat/syndromes.py). Summer-behavioural types (injury, violence, drowning) can pass the screen.</p>
{zblock}
{'<h2>Next 7 days</h2>' + _table(fct, {"temp": "{:.1f}", "mu_base": "{:.1f}", "mu_full": "{:.1f}", "heat_expected": "{:+.1f}"}) if fct is not None else ''}

<h2>Method and limits</h2>
<ul>
<li>Dispatch codes are what callers and crews report, not diagnoses. The outcome is heat-associated EMS demand, not confirmed heat illness.</li>
<li>Alarm thresholds ignore parameter uncertainty and use one overdispersion estimate per weekly refit; expect a few false alarms per year by design (α = {ctx['alpha']}).</li>
<li>Temperature is citywide (one station or grid point). Zip-level exposure differences, such as urban heat islands, appear only through the zip ratios.</li>
<li>The threshold model is a simplification of a distributed-lag nonlinear model.</li>
<li>Mar–Jul 2020 is excluded from all fits because of COVID-era disruption to EMS demand.</li>
</ul>
</main>"""
    path = out / "report.html"
    path.write_text(body)

    md = [f"EMS Heat Watch: data to {fresh['last_complete']} ({fresh['lag_days']} day lag)",
          f"Primary outcome: {prim}"]
    for k, r in R.items():
        md.append(f"- {k}: {(r['rr'] - 1) * 100:+.1f}% per °C above {r['T0']:.1f} °C "
                  f"({(r['rr_lo'] - 1) * 100:+.1f} to {(r['rr_hi'] - 1) * 100:+.1f})")
    if len(bt):
        md.append("Heat waves (primary outcome):")
        for _, b in btp.iterrows():
            md.append(f"- {b['onset']} ({b['days']} d, peak {b['peak Tmax °C']:.1f} °C): first alarm day "
                      f"{b['first alarm (day)']}, excess {b['observed excess']:+.0f} calls vs {b['model-predicted heat calls']:.0f} predicted")
    md.append(f"Next 7 days: {fc_heat:.0f} heat-attributable calls expected (peak {fc_peak:.1f} °C)")
    (out / "summary.md").write_text("\n".join(md) + "\n")
    return path
