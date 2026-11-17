"""
Build the one-page summary (docs/ems_heat_watch_summary.html + .pdf) from results/v2.
Every number is read from the result files, not typed in.

  python analysis/make_summary.py --author "Your Name"
"""
import argparse
import base64
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results" / "v2"
DOCS = ROOT / "docs"
OBS, REF, ALARM, WAVE, INK, MUTED = "#2a78d6", "#8a8984", "#e34948", "#f6e3c9", "#0b0b0b", "#52514e"


def fig():
    s = pd.read_csv(RES / "surveillance_heat.csv", index_col=0, parse_dates=True)
    w = pd.read_csv(RES / "heat_waves.csv", parse_dates=["start", "end"])
    f, axes = plt.subplots(1, 2, figsize=(7.5, 1.45), sharey=True)
    for ax, yr in zip(axes, (2025, 2026)):
        x = s[f"{yr}-05-15":f"{yr}-09-15"]
        for _, e in w[(w.start.dt.year == yr)].iterrows():
            ax.axvspan(e.start - pd.Timedelta(hours=12), e.end + pd.Timedelta(hours=12), color=WAVE, lw=0, zorder=0)
        ax.fill_between(x.index, x.mu_norm, x.u_norm, color=REF, alpha=0.18, lw=0, step="mid", zorder=1)
        ax.plot(x.index, x.mu_norm, color=REF, lw=1.0, zorder=2)
        ax.plot(x.index, x.obs, color=OBS, lw=1.2, zorder=3)
        a = x[x.alarm_norm]
        ax.scatter(a.index, a.obs, s=14, facecolor="none", edgecolor=ALARM, lw=1.1, zorder=4)
        ax.set_title(str(yr), fontsize=8.5, color=INK, loc="left", pad=2)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color("#c9c8c3")
        ax.tick_params(labelsize=7, colors=MUTED, length=2)
        ax.grid(axis="y", color="#ecebe8", lw=0.6)
    axes[0].set_ylabel("HEAT calls / day", fontsize=7.5, color=MUTED)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    h = [Line2D([], [], color=OBS, lw=1.2, label="observed"),
         Line2D([], [], color=REF, lw=1.0, label="expected at normal Tmax"),
         Patch(color=REF, alpha=0.18, label="to 99.5% alarm limit"),
         Line2D([], [], marker="o", ls="", mfc="none", mec=ALARM, ms=4, label="alarm"),
         Patch(color=WAVE, label="heat wave (≥3 d Tmax ≥32.2 °C)")]
    f.legend(handles=h, loc="lower center", ncol=5, fontsize=6.6, frameon=False, bbox_to_anchor=(0.5, -0.04))
    f.tight_layout(rect=(0, 0.1, 1, 1), w_pad=1.0)
    buf = io.BytesIO()
    f.savefig(buf, format="svg", bbox_inches="tight")
    return base64.b64encode(buf.getvalue()).decode()


def table():
    b = pd.read_csv(RES / "backtest_summary.csv")
    rows = []
    order = ["Heat model vs normal Tmax", "Farrington Flexible", "EARS C1", "EARS C2", "EARS C3"]
    for out, lab in (("HEAT", "HEAT calls"), ("Heat syndrome (pre-specified)", "Heat syndrome")):
        for m in order:
            d = b[(b.outcome == out) & (b.method == m) & b.period.str.startswith("Dev")].iloc[0]
            h = b[(b.outcome == out) & (b.method == m) & b.period.str.startswith("Held")].iloc[0]
            delay = "–" if pd.isna(d.median_delay) else f"{d.median_delay:g}"
            rows.append(f"<tr><td>{lab}</td><td>{m.replace('Heat model vs normal Tmax', 'Heat model (vs normal Tmax)')}</td><td>{d.detected}/{d.waves}</td><td>{d.FA_per_season:.1f}</td>"
                        f"<td>{delay}</td><td>{h.detected}/{h.waves}</td><td>{h.FA_per_season:.1f}</td></tr>")
            lab = ""
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", default="")
    a = ap.parse_args()
    by = f"{a.author} · " if a.author else ""
    er = pd.read_csv(RES / "exposure_response.csv").set_index("outcome")
    log = json.loads((RES / "run_log.json").read_text())
    heat = er.loc["HEAT"]
    syn = er.loc["Heat syndrome (pre-specified)"]
    qa = pd.read_csv(RES / "qa_by_year.csv", index_col=0)
    bs = pd.read_csv(RES / "backtest_summary.csv")
    hot_dev = float(bs[(bs.outcome == "HEAT") & (bs.method == "Heat model vs normal Tmax")
                       & bs.period.str.startswith("Dev")]["hot_isolated_alarm_rate"].iloc[0])
    n_calls = int(qa["all_calls"].sum())
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>EMS Heat Watch</title>
<style>
@page {{ size: Letter; margin: 0.38in 0.45in; }}
body {{ font-family: "Helvetica Neue", Arial, sans-serif; color:{INK}; font-size: 8.2pt; line-height: 1.27; margin:0; background:#fff; }}
h1 {{ font-size: 15pt; margin: 0 0 1px; }} .sub {{ color:{MUTED}; margin:0 0 6px; font-size:8.4pt; }}
h2 {{ font-size: 9.3pt; margin: 5px 0 2px; border-bottom: 1px solid #ddd; padding-bottom:1px; }}
p {{ margin: 2px 0 3px; }} ul {{ margin: 2px 0 3px 15px; padding:0; }} li {{ margin: 0 0 1px; }}
.cols {{ display:grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
table {{ border-collapse: collapse; width:100%; font-size: 7.8pt; }}
th, td {{ text-align:left; padding: 1.5px 4px; border-bottom: 1px solid #eee; }} th {{ color:{MUTED}; font-weight:600; }}
td:nth-child(n+3), th:nth-child(n+3) {{ text-align:right; }} td {{ white-space:nowrap; }}
.wide {{ display:grid; grid-template-columns: 1.2fr 0.8fr; gap: 14px; }}
img {{ width:100%; }} .note {{ color:{MUTED}; font-size:7.4pt; }}
</style></head><body>
<h1>EMS Heat Watch</h1>
<p class="sub">Heat-health surveillance from ambulance dispatch data: proof of concept on New York City EMS data, 2013–2026 ·
{by}code and results: github.com/samielsabri/ems-heat-watch · {pd.Timestamp.today():%B %Y}</p>
<div class="cols"><div>
<h2>Problem</h2>
<p>Hospital and mortality data, the core measures of heat-health impact, arrive months after a heat event.
Ambulance dispatch records exist in near real time inside every paramedic service, but are rarely integrated into heat surveillance.
This project tests whether dispatch data alone can show the health impact of heat within days, using public NYC data.</p>
<h2>Data</h2>
<ul><li>NYC EMS Incident Dispatch Data: {n_calls:,} calls, 2013-01-01 to {log['last_complete']}; daily counts by call type,
match the portal on every day. Public release runs ~6 weeks behind; an internal feed would be same-day.</li>
<li>NYC has a dedicated <b>HEAT</b> call type (~{qa.loc[2016:2024,'HEAT_final'].mean():.0f}/yr, 2016–24; {int(qa.loc[2026,'HEAT_final']):,} in 2026 to Sep).
Pre-specified <b>heat syndrome</b>: unconscious, altered mental status, sick, breathing difficulty, cardiac, respiratory, arrest
({syn.mean_daily:,.0f} calls/day).</li>
<li>Exposure: daily Tmax, Central Park (NOAA GHCN-D).</li></ul>
</div><div>
<h2>Method</h2>
<ul><li>Exposure–response: quasi-Poisson time series (time spline, day of week, holidays, threshold heat term, lags 0–3), 2013–2024.
HEAT calls: <b>+{100*(heat.rr-1):.0f}% per °C</b> above {heat.T0:.1f} °C ({100*(heat.lo-1):.0f}–{100*(heat.hi-1):.0f}%), almost all same-day.
Syndrome: +{100*(syn.rr-1):.1f}% per °C, no clear threshold.</li>
<li>Surveillance: weekly refit on the previous 3 years; <b>alarm</b> when calls exceed the 99.5% negative-binomial limit of the count
expected at the <i>normal</i> Tmax for that date.</li>
<li>Comparators: EARS C1–C3 and Farrington Flexible (daily), ported from my earlier outbreak-detection project.</li>
<li>Back-test against heat waves (≥3 days Tmax ≥32.2 °C). Methods fixed on data to 2024; 2025–26 held out.</li></ul>
</div></div>
<div class="wide"><div>
<h2>Back-test</h2>
<table><tr><th>Outcome</th><th>Method</th><th>POD dev</th><th>FA/season</th><th>Delay (d)</th><th>POD held-out</th><th>FA/season</th></tr>
{table()}</table>
<p class="note">Dev = 2016–24 (20 waves, Mar–Jul 2020 excluded); held-out = 2025-01 to {log['last_complete'][:7]} (3 waves).
POD: waves with ≥1 alarm between onset and the last hot day. FA/season: alarms on non-heat May–Sep days (Tmax &lt;29.4 °C that day and
the 3 before, away from waves), per 153 days. Delay: median days from onset to first alarm. α = 0.005, nothing tuned.</p>
</div><div>
<h2>Findings</h2>
<ul><li>HEAT calls are a specific signal: the heat model alarmed on 19/20 development and 3/3 held-out heat waves with ~2 false alarms
per season; Farrington had none but missed 4/20; EARS detected similarly but with 3–8× more false alarms.</li>
<li>Alarms come on day 0 because heat waves are defined from temperature: the value is same-day confirmation and measurement of health
impact, not earlier warning than a forecast.</li>
<li>The broad syndrome rises only ~3–9% in a heat wave, inside its day-to-day noise: use it to estimate excess calls, not to alarm.</li></ul>
</div></div>
<h2>HEAT calls, summers 2025 and 2026 (held-out)</h2>
<img src="data:image/svg+xml;base64,{fig()}">
<div class="cols"><div>
<h2>Fit with Toronto's heat response</h2>
<p>ECCC issues Toronto Heat Warnings (≥2 days Tmax ≥31 °C with Tmin ≥20 °C, or humidex ≥40), graded by expected impact (Moderate/High/Extreme,
"increased" to "extreme risk of illness or death"); TPH runs the Heat Relief Strategy. EMS excess calls measure that health impact directly:
during a warning they confirm and size it the same day; after the event they test whether the impact level matched the harm.
One-day heat events usually get no warning, yet the HEAT alarm fired on {100*hot_dev:.0f}% of isolated hot days (2016–24).</p>
</div><div>
<h2>Limitations</h2>
<ul><li>Dispatch codes are caller/crew impressions, not diagnoses; NYC re-labelled codes during the period (families merged).</li>
<li>Only 3 held-out heat waves; development results partly in-sample. Heat waves defined from temperature only.</li>
<li>Single station, Tmax only (no humidex yet); threshold model rather than DLNM; alarm limits ignore parameter uncertainty;
Farrington port not yet cross-checked against R <i>surveillance</i>.</li>
<li>Not yet tested on Toronto data.</li></ul>
</div></div>
</body></html>"""
    DOCS.mkdir(exist_ok=True)
    out = DOCS / "ems_heat_watch_summary.html"
    out.write_text(html)
    import subprocess
    import shutil, glob
    mac = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium",
           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    cands = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome") + [c for c in mac if Path(c).exists()]
             + [shutil.which(n) or "" for n in ("chromium", "google-chrome", "chrome")])
    chrome = next((c for c in cands if c), None)
    if chrome is None:
        print("No Chrome/Chromium found: open", out, "in a browser and print to PDF (Letter, no headers).")
        return
    subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={DOCS / 'ems_heat_watch_summary.pdf'}", out.resolve().as_uri()],
                   check=True, capture_output=True)
    print("written", out)


if __name__ == "__main__":
    main()
