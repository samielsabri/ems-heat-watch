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

INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e7e5e0"
OBS, BASE, HEATC, ALARM, WAVE, TEMPC = "#0b0b0b", "#2a78d6", "#eb6834", "#e34948", "#fbe6d6", "#52514e"

plt.rcParams.update({
    "font.size": 9.5, "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.titlesize": 9.5, "axes.titleweight": "normal", "axes.titlecolor": MUTED,
    "axes.titlelocation": "left", "legend.frameon": False, "svg.fonttype": "none",
})


def _png(fig):
    """Vector output (SVG, real text) so figures stay sharp at any size. Name kept for call sites."""
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _legend_below(fig, handles, ncol, ax=None, y=-0.16):
    """Legend outside the plot area. With ax: anchored under that axis (bbox_inches='tight' grows the canvas)."""
    kw = dict(handles=handles, ncol=ncol, fontsize=8.5, handlelength=1.8, columnspacing=1.6)
    if ax is not None:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, y), **kw)
    else:
        fig.legend(loc="lower center", bbox_to_anchor=(0.5, -0.01), **kw)


def _shade_waves(ax, events, lo, hi):
    for _, e in events.iterrows():
        if e["end"] >= lo and e["start"] <= hi:
            ax.axvspan(e["start"] - pd.Timedelta(hours=12), e["end"] + pd.Timedelta(hours=12),
                       color=WAVE, zorder=0, lw=0)


def fig_operational(ctx, name, days=60):
    """Left: the last `days` days of EMS data. Right (if a forecast exists): the next 7 days.
    The gap between the last EMS day and today (publication lag) is stated, not plotted."""
    from matplotlib.gridspec import GridSpec
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    r = ctx["results"][name]
    s = r["surv"].iloc[-days:]
    fc = r["forecast"]
    has_fc = fc is not None and len(fc) > 0
    temp = ctx["temp"]
    ref, uref = ("mu_norm", "u_norm") if "mu_norm" in s else ("mu_base", "u_base")

    fig = plt.figure(figsize=(9.6, 4.9))
    gs = GridSpec(2, 2 if has_fc else 1, figure=fig, width_ratios=[5, 1.25] if has_fc else [1],
                  height_ratios=[3, 1.2], wspace=0.07, hspace=0.12)
    ax = fig.add_subplot(gs[0, 0])
    axt = fig.add_subplot(gs[1, 0], sharex=ax)
    lo, last = s.index.min(), s.index.max()

    _shade_waves(ax, ctx["events"], lo, last)
    ax.fill_between(s.index, s[ref], s[uref], color=BASE, alpha=0.12, lw=0, step="mid")
    ax.plot(s.index, s[ref], color=BASE, lw=1.6)
    ax.plot(s.index, s["mu_full"], color=HEATC, lw=1.4, ls=(0, (4, 2)))
    ax.plot(s.index, s["obs"], color=OBS, lw=1.2, marker="o", ms=2.6)
    al = s[s["alarm"]]
    ax.scatter(al.index, al["obs"], s=70, facecolor="none", edgecolor=ALARM, lw=1.8, zorder=5)
    ax.set_ylabel("calls per day")
    ax.set_title(f"EMS data, {lo:%d %b} to {last:%d %b %Y}")
    ax.set_ylim(bottom=0)
    plt.setp(ax.get_xticklabels(), visible=False)

    tt = temp[lo:last]
    axt.plot(tt.index, tt.values, color=TEMPC, lw=1.3)
    axt.axhline(r["T0"], color=MUTED, lw=0.8, ls=(0, (2, 2)))
    axt.annotate(f"heat threshold T0 {r['T0']:.1f} °C", (lo, r["T0"]), xytext=(2, 3), textcoords="offset points",
                 color=MUTED, fontsize=8)
    axt.set_ylabel("Tmax °C")
    axt.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=2))
    axt.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    if has_fc:
        axf = fig.add_subplot(gs[0, 1], sharey=ax)
        axft = fig.add_subplot(gs[1, 1], sharey=axt, sharex=axf)
        axf.plot(fc.index, fc["mu_norm"], color=BASE, lw=1.6, marker="o", ms=2.6)
        axf.plot(fc.index, fc["mu_full"], color=HEATC, lw=1.4, ls=(0, (4, 2)), marker="o", ms=2.6)
        lag = (fc.index.min() - last).days
        axf.set_title("Forecast, next 7 days")
        axf.text(0.02, 0.97, f"{lag}-day publication gap\nnot shown", transform=axf.transAxes, va="top",
                 fontsize=8, color=MUTED)
        plt.setp(axf.get_yticklabels(), visible=False)
        plt.setp(axf.get_xticklabels(), visible=False)
        axft.plot(fc.index, fc["temp"], color=TEMPC, lw=1.3, ls=(0, (1, 1.5)), marker="o", ms=2.6)
        axft.axhline(r["T0"], color=MUTED, lw=0.8, ls=(0, (2, 2)))
        plt.setp(axft.get_yticklabels(), visible=False)
        axft.xaxis.set_major_locator(mdates.DayLocator(interval=3))
        axft.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        for a_ in (axf, axft):
            a_.spines["left"].set_visible(False)
            a_.tick_params(axis="y", length=0)

    handles = [Line2D([], [], color=OBS, lw=1.2, marker="o", ms=3, label="observed calls"),
               Line2D([], [], color=BASE, lw=1.6, label="expected at normal Tmax"),
               Patch(color=BASE, alpha=0.12, label="up to the 99.5% alarm limit"),
               Line2D([], [], color=HEATC, lw=1.4, ls=(0, (4, 2)), label="expected given actual Tmax"),
               Line2D([], [], ls="", marker="o", ms=7, mfc="none", mec=ALARM, mew=1.8, label="alarm")]
    ev = ctx["events"]
    if len(ev) and ((ev["end"] >= lo) & (ev["start"] <= last)).any():
        handles.append(Patch(color=WAVE, label="heat wave"))
    _legend_below(fig, handles, 3)
    fig.subplots_adjust(bottom=0.2)
    return _png(fig)


def fig_timeline(ctx, name):
    r = ctx["results"][name]
    s = r["surv"]
    fig, ax = plt.subplots(figsize=(9.6, 3.2))
    _shade_waves(ax, ctx["events"], s.index.min(), s.index.max())
    ax.plot(s.index, s["obs"], color=OBS, lw=0.8, label="observed calls")
    ref = "mu_norm" if "mu_norm" in s else "mu_base"
    ax.plot(s.index, s[ref], color=BASE, lw=1.4, label="expected at normal Tmax")
    al = s[s["alarm"]]
    ax.scatter(al.index, al["obs"], s=22, facecolor="none", edgecolor=ALARM, lw=1.4, zorder=5, label="alarm")
    from matplotlib.patches import Patch
    ax.set_ylabel("calls per day")
    ax.set_ylim(bottom=0)
    h, _ = ax.get_legend_handles_labels()
    _legend_below(fig, h + [Patch(color=WAVE, label="heat wave")], 4, ax=ax, y=-0.12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.tight_layout()
    return _png(fig)


def fig_curves(ctx):
    """Heat-coded calls rise ~1000-fold over the range, broad outcomes a few percent: separate panels."""
    temps = np.linspace(15, 38, 100)
    cols = ["#eb6834", "#2a78d6", "#1baf7a", "#6250d6"]
    items = list(ctx["results"].items())
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.3), gridspec_kw={"wspace": 0.28})
    for k, ((name, r), c) in enumerate(zip(items, cols)):
        ax = a1 if k == 0 else a2
        cv = r["retro"].curve(temps)
        ax.plot(cv["temp"], cv["rr"], color=c, lw=1.8, label=name)
        ax.fill_between(cv["temp"], cv["lo"], cv["hi"], color=c, alpha=0.15, lw=0)
    a1.set_yscale("log")
    a1.set_title(items[0][0] + " (log scale)")
    a2.set_title("Broader outcomes")
    for ax in (a1, a2):
        ax.axhline(1, color=MUTED, lw=0.8)
        ax.set_xlabel("sustained daily Tmax, °C")
    a1.set_ylabel("rate ratio vs below T0")
    if len(items) > 1:
        _legend_below(fig, a2.get_legend_handles_labels()[0], 1, ax=a2, y=-0.22)
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
        (("Forecast excess heat calls, next 7 days", f"{fc_heat:+.0f}", f"vs normal Tmax; peak forecast Tmax {fc_peak:.1f} °C", fc_heat >= 5)
         if fc is not None and len(fc) else
         ("7-day outlook", "n/a", "no forecast weather in this run (use --weather open-meteo)", False)),
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
                                         "expected_normal", "excess_obs", "heat_expected"]].copy()
        btp["days_to_first_alarm"] = btp["days_to_first_alarm"].astype(object).where(btp["days_to_first_alarm"].notna(), "none")
        btp.columns = ["onset", "days", "peak Tmax °C", "alarm days", "first alarm (day)", "observed",
                       "expected at normal Tmax", "observed excess", "model-predicted excess"]
        rows = []
        for k, g in bt.groupby("outcome", sort=False):
            hit = g["days_to_first_alarm"].notna()
            rows.append({"outcome": k, "heat waves alarmed": f"{int(hit.sum())}/{len(g)}",
                         "waves with excess > 0": f"{int((g['excess_obs'] > 0).sum())}/{len(g)}",
                         "median first alarm (day)": float(g.loc[hit, "days_to_first_alarm"].median()) if hit.any() else None,
                         "observed excess": g["excess_obs"].sum(), "model-predicted": g["heat_expected"].sum()})
        bts_sum = pd.DataFrame(rows)

    fct = None
    if fc is not None and len(fc):
        fct = fc.reset_index().rename(columns={"index": "date"})
        fct["date"] = fct["date"].dt.strftime("%a %d %b")
        fct = fct[["date", "temp", "mu_norm", "mu_full", "heat_expected"]].rename(
            columns={"temp": "Tmax", "mu_norm": "expected at normal Tmax", "mu_full": "expected", "heat_expected": "excess"})

    zblock = ""
    if ctx.get("zip_pooled") is not None and len(ctx["zip_pooled"]):
        key = f"{len(ctx['zres'])} evaluated heat waves (pooled)"
        zr = ctx["zip_pooled"]
        zt = zr.head(12).reset_index()
        zblock = (f"<h2>Where: zip codes across {key}</h2>"
                  f"<p class='sub'>Exploratory, and underpowered with {len(ctx['zres'])} heat waves. Indirectly standardised ratios for heat-coded calls plus the pre-specified heat syndrome "
                  f"({html.escape(', '.join(ctx['zip_types']))}), since heat-coded calls alone are too sparse per zip. Expected counts use each zip's "
                  f"share on ordinary summer days (Jun–Sep of that year and the year before, Tmax &lt; 29.4 °C, outside the wave), scaled to the citywide expectation. "
                  f"<code>relative</code> above 1 means the zip was hit harder than the city as a whole; check the confidence interval before reading anything into it.</p>"
                  f"<div class='grid2'><img src='data:image/svg+xml;base64,{fig_zips(zr, 'Top zips, all evaluated heat waves')}'>"
                  + _table(zt[["zipcode", "obs", "expected", "sir", "sir_lo", "sir_hi", "relative"]],
                           {"expected": "{:.1f}", "sir": "{:.2f}", "sir_lo": "{:.2f}", "sir_hi": "{:.2f}",
                            "relative": "{:.2f}"}) + "</div>")

    scr = ctx["screen"].head(15)[["call_type", "mean_daily", "rr", "rr_lo", "rr_hi", "q"]].copy()
    for c in ("rr", "rr_lo", "rr_hi"):
        scr[c] = (scr[c] - 1) * 100
    scr["flagged"] = np.where((ctx["screen"].head(15)["q"] < 0.05) & (ctx["screen"].head(15)["rr"] >= 1.02), "yes", "")
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
<h2>{html.escape(prim)}: latest data{' and 7-day outlook' if fresh.get('has_forecast') else ''}</h2>
<img src="data:image/svg+xml;base64,{fig_operational(ctx, prim)}">
<p class="note">Blue line: calls expected for this date at its normal Tmax (trend, season, weekday, holidays, normal temperature).
Shaded band: from that expectation up to the {100 * (1 - ctx['alpha']):.1f}% alarm limit. Orange dashed: calls expected given the observed
temperature. Circles: alarm days (observed above the band). Lower panel: daily Tmax with the heat threshold T0. {'Right-hand panels: the 7-day forecast; the days between the last published EMS record and today are not shown.' if fresh.get('has_forecast') else 'No forecast weather in this run, so no outlook is shown.'}</p>

<h2>Timeliness compared with a six-month lag</h2>
<p>As of {fresh['asof']}, this pipeline sees data to {fresh['last_complete']} ({fresh['lag_days']} day lag). It covers
{fresh['visible_now']} of {len(ctx['events'])} heat waves in the record. With a six-month lag, only {fresh['visible_with_6mo_lag']} would be visible,
and none from the current season.</p>

<h2>Heat waves in the evaluation period</h2>
<p class="sub">Every heat wave since evaluation began, scored prospectively: each week's model saw only earlier data.</p>
{_table(btp, {"peak Tmax °C": "{:.1f}", "observed": "{:.0f}", "expected at normal Tmax": "{:.0f}", "observed excess": "{:+.0f}", "model-predicted excess": "{:+.0f}"}) if len(btp) else "<p>No heat waves in the evaluation period.</p>"}
<p class="note">{html.escape(prim)}. First alarm counts from heat wave onset (0 = alarm on day one). Window: the wave plus three days.
Observed excess = observed minus expected at normal Tmax; model-predicted excess = what the temperature model expected minus the same normal-Tmax
expectation. Close agreement means the model sizes the impact correctly.</p>
<h2>All outcomes</h2>
{_table(bts_sum, {"median first alarm (day)": "{:.0f}", "observed excess": "{:+.0f}", "model-predicted": "{:+.0f}"}) if len(bts_sum) else ""}
<p class="note">Excess is measured against the count expected at normal Tmax over each wave plus three days. Broader outcomes carry a
small heat effect relative to their day-to-day variation, so their excess is inconsistent between waves and rarely crosses the alarm limit:
use them to size impact after the fact, not to alarm.</p>

<h2>{html.escape(prim)}: prospective surveillance, evaluation period</h2>
<img src="data:image/svg+xml;base64,{fig_timeline(ctx, prim)}">

<h2>Heat effect by outcome</h2>
<img src="data:image/svg+xml;base64,{fig_curves(ctx)}">
<div>
{_table(eff, {"mean_per_day": "{:.1f}", "T0": "{:.1f}", "pct_per_degC": "{:+.1f}", "lo": "{:+.1f}", "hi": "{:+.1f}", "overdispersion": "{:.2f}"})}</div>
<p class="note">Cumulative change in daily calls per °C of sustained Tmax above threshold T0 (lags 0–3), from a quasi-Poisson time-series
model with a natural spline of time, day of week and holidays. Fitted on the training period only.</p>

<h2>Which call types respond to heat</h2>
<div class="grid2"><img src="data:image/svg+xml;base64,{fig_screen(ctx)}">
{_table(scr, {"mean_daily": "{:.1f}", "%/°C": "{:+.1f}", "lo": "{:+.1f}", "hi": "{:+.1f}", "q": "{:.3g}"})}</div>
<p class="note">Exploratory. Each final call type used throughout the training years (code variants merged) with ≥1 call/day was
screened on the training period; listed as heat-sensitive if FDR q &lt; 0.05 and ≥ +2%/°C. The surveillance syndrome is NOT taken
from this screen: it is pre-specified (emsheat/syndromes.py). Summer-behavioural types (injury, violence, drowning) can pass the screen.</p>
{zblock}
{'<h2>Next 7 days</h2>' + _table(fct, {"Tmax": "{:.1f}", "expected at normal Tmax": "{:.1f}", "expected": "{:.1f}", "excess": "{:+.1f}"}) if fct is not None else ''}

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
                      f"{b['first alarm (day)']}, excess {b['observed excess']:+.0f} calls vs {b['model-predicted excess']:+.0f} predicted (vs normal Tmax)")
    if fc is not None and len(fc):
        md.append(f"Next 7 days: {fc_heat:+.0f} calls vs normal Tmax expected (peak forecast {fc_peak:.1f} °C)")
    else:
        md.append("Next 7 days: no forecast weather in this run")
    (out / "summary.md").write_text("\n".join(md) + "\n")
    return path
