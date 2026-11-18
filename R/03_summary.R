# Figure and one-page summary, built from output/.
#   docs/figure.png, docs/summary.html, and docs/summary.pdf if Chrome/Edge/Brave is installed
#   (with Safari only, the page opens in Safari: File > Export as PDF)
# Usage: Rscript R/03_summary.R ["Name"]   (or Source it in RStudio)

args <- commandArgs(trailingOnly = TRUE)
author <- if (length(args)) args[1] else "Sami El Sabri"
dir.create("docs", showWarnings = FALSE)
ind <- read.csv("output/daily_indicator.csv", colClasses = c(date = "Date"))
waves <- read.csv("output/heat_waves.csv", colClasses = c(start = "Date", end = "Date"))
bt <- read.csv("output/backtest.csv")
heat <- read.csv("data/heat_calls.csv", colClasses = c("Date", "integer", "integer"))
hb <- read.csv("output/hidden_burden.csv")
hb_all <- hb[hb$period == "all", ]

# --- figure: heat calls in the two held-out summers ---
ink <- "#0b0b0b"; blue <- "#2a78d6"; red <- "#e34948"; wave <- "#fbe6d6"; grey <- "#6b6a66"
# quartz on a Mac, cairo elsewhere: neither needs XQuartz on macOS
png("docs/figure.png", width = 7.5, height = 1.7, units = "in", res = 300,
    type = if (capabilities("aqua")) "quartz" else "cairo")
par(mfrow = c(1, 2), mar = c(2.2, 3.2, 1.6, 0.6), mgp = c(2, 0.5, 0), tcl = -0.2, cex.axis = 0.75,
    col.axis = grey, fg = "#c9c8c3")
ymax <- max(ind$heat_calls[ind$date >= as.Date("2025-05-15")], na.rm = TRUE)
for (yr in 2025:2026) {
  x <- ind[ind$date >= as.Date(paste0(yr, "-05-15")) & ind$date <= as.Date(paste0(yr, "-09-15")), ]
  plot(x$date, x$heat_calls, type = "n", ylim = c(0, ymax), xlab = "", ylab = if (yr == 2025) "heat calls per day" else "",
       col.lab = grey, cex.lab = 0.8, bty = "l", las = 1, xaxt = "n")
  axis.Date(1, at = seq(as.Date(paste0(yr, "-06-01")), by = "month", length.out = 4), format = "%b")
  grid(nx = NA, ny = NULL, col = "#ecebe8", lty = 1)
  for (i in which(format(waves$start, "%Y") == yr))
    rect(waves$start[i] - 0.5, 0, waves$end[i] + 0.5, ymax, col = wave, border = NA)
  polygon(c(x$date, rev(x$date)), c(x$expected_normal_tmax, rev(x$upper_limit)),
          col = adjustcolor(blue, 0.15), border = NA)
  lines(x$date, x$expected_normal_tmax, col = blue, lwd = 1.4)
  lines(x$date, x$heat_calls, col = ink, lwd = 0.9)
  a <- x[x$alarm_indicator, ]
  points(a$date, a$heat_calls, col = red, cex = 0.7, lwd = 1.2)
  mtext(paste("Summer", yr), side = 3, adj = 0, line = 0.2, cex = 0.75, col = grey)
}
dev.off()

# --- numbers for the text, all from output/ ---
get <- function(p, m, col) bt[bt$period == p & bt$method == m, col]
ears <- c("ears_c1", "ears_c2", "ears_c3")
rng <- function(p, col, fmt = "%d") {
  v <- range(sapply(ears, function(m) get(p, m, col)))
  if (v[1] == v[2]) sprintf(fmt, v[1]) else paste0(sprintf(fmt, v[1]), "–", sprintf(fmt, v[2]))
}
row <- function(label, m) sprintf(
  "<tr><td>%s</td><td>%d/%d</td><td>%.1f</td><td>%d/%d</td><td>%.1f</td></tr>", label,
  get("development", m, "detected"), get("development", m, "heat_waves"), get("development", m, "false_alarms_per_summer"),
  get("heldout", m, "detected"), get("heldout", m, "heat_waves"), get("heldout", m, "false_alarms_per_summer"))
ears_row <- sprintf("<tr><td>EARS C1–C3</td><td>%s/%d</td><td>%s</td><td>%s/%d</td><td>%s</td></tr>",
  rng("development", "detected"), get("development", "indicator", "heat_waves"),
  rng("development", "false_alarms_per_summer", "%.1f"),
  rng("heldout", "detected"), get("heldout", "indicator", "heat_waves"), rng("heldout", "false_alarms_per_summer", "%.1f"))
last <- max(heat$date)
lag <- as.numeric(Sys.Date() - last)
per_year <- 10 * round(0.1 * mean(tapply(heat$heat_calls, format(heat$date, "%Y"), sum)[as.character(2016:2024)]))
by <- if (nzchar(author)) paste0(author, " · ") else ""
fig <- paste0('<img src="data:image/png;base64,',
              jsonlite::base64_enc(readBin("docs/figure.png", "raw", file.size("docs/figure.png"))), '">')

html <- sprintf('<!doctype html><html><head><meta charset="utf-8"><title>EMS Heat Watch</title><style>
@page { size: Letter; margin: 0.35in 0.5in; }
:root { --ink: #0b0b0b; --muted: #57564f; --line: #e6e3dc; --blue: #2a78d6; --tint: #f3f7fc; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: var(--ink); font-size: 9.4pt; line-height: 1.38;
       margin: 0; background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { max-width: 7.4in; margin: 0 auto; }
header { border-bottom: 2px solid var(--blue); padding-bottom: 8px; margin-bottom: 12px; }
h1 { font-size: 19pt; margin: 0 0 3px; letter-spacing: -0.01em; }
h2 { font-size: 10.5pt; margin: 12px 0 4px; }
.sub { color: var(--muted); margin: 0; }
p { margin: 3px 0 6px; } ul { margin: 3px 0 6px 18px; padding: 0; } li { margin-bottom: 3px; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; margin: 4px 0 6px; }
.tile { background: var(--tint); border-radius: 8px; padding: 9px 12px; }
.tile b { display: block; font-size: 16pt; color: var(--blue); margin-bottom: 1px; white-space: nowrap; }
.tile span, .note, figcaption { color: var(--muted); font-size: 8.6pt; }
table { border-collapse: collapse; width: 100%%; font-size: 9.2pt; font-variant-numeric: tabular-nums; }
th, td { padding: 4px 8px; border-bottom: 1px solid var(--line); text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--muted); font-weight: 600; }
thead tr:first-child th { text-align: center; border-bottom: 1px solid var(--line); padding-bottom: 2px; }
thead tr:first-child th:first-child { border-bottom: none; }
tbody tr:first-child td { font-weight: 600; }
figure { margin: 10px 0 4px; border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px 6px; }
figure img { width: 100%%; height: auto; display: block; } figcaption { margin-top: 4px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media screen {
  html { background: #eeece7; }
  body { font-size: 10.5pt; }
  .page { max-width: 820px; margin: 32px auto; background: #fff; padding: 40px 48px; border-radius: 10px;
          box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 8px 24px rgba(0,0,0,.06); }
}
@media print {
  body { font-size: 8.8pt; line-height: 1.3; } h1 { font-size: 17pt; } h2 { margin: 7px 0 3px; }
  header { padding-bottom: 6px; margin-bottom: 8px; } .tile { padding: 6px 9px; } .tile b { font-size: 14pt; }
  figure { padding: 4px 8px 4px; margin: 6px 0 2px; } li { margin-bottom: 2px; }
}
@media screen and (max-width: 700px) {
  .page { margin: 0; padding: 20px 16px; border-radius: 0; } .cols { grid-template-columns: 1fr; }
  .tiles { grid-template-columns: 1fr 1fr; }
}
</style></head><body><main class="page">
<header><h1>EMS Heat Watch</h1>
<p class="sub">Can paramedic data give early warning of heat&#39;s health impact, and measure the burden that heat-coded
records miss? A proof of concept on public New York City data.<br>%sgithub.com/samielsabri/ems-heat-watch</p></header>
<div class="tiles">
<div class="tile"><b>Day 1</b><span>heat waves flagged on day one: %d/%d held out (2025–26), %d/%d in 2016–24</span></div>
<div class="tile"><b>About 1 in 3</b><span>of heat-associated excess calls carry a heat code (%d%%, 95%% CI %d–%d%%)</span></div>
<div class="tile"><b>~%.0f per summer</b><span>alerts outside heat waves (2016–24): low alert fatigue</span></div>
<div class="tile"><b>Days, not months</b><span>public NYC data is %d days behind; an internal feed would be same-day</span></div>
</div>
<h2>What I did</h2>
<ul>
<li><b>Data:</b> daily NYC ambulance calls, 2010 to %s: coded <i>heat</i> (about %d a year), and heat-related calls with other
codes chosen in advance (unconscious, altered mental status, sick, breathing, cardiac, respiratory, arrest). Central Park Tmax.</li>
<li><b>Early warning:</b> each day, compare heat calls with the number expected on a normal-temperature day at that time of year;
alert when above the expected range. Tested by replaying 2016–2026 day by day on past data only, against every heat wave
(3+ days at 32 °C or more). Nothing was tuned on 2025–26.</li>
<li><b>Hidden burden:</b> the same model on the other heat-related calls; during each heat wave, compare their excess over a
normal-temperature day with the excess in heat-coded calls.</li>
</ul>
<h2>Results</h2>
<table><thead><tr><th></th><th colspan="2">2016–24 (development)</th><th colspan="2">2025–26 (held out)</th></tr>
<tr><th>Method</th><th>Heat waves flagged</th><th>Alerts / summer*</th><th>Heat waves flagged</th><th>Alerts / summer*</th></tr></thead>
<tbody>%s%s%s</tbody></table>
<p class="note">*Outside heat waves. Farrington Flexible is the standard method for routine communicable disease surveillance;
EARS is the CDC&#39;s syndromic method (both from the R <i>surveillance</i> package). The new indicator catches more heat waves
than Farrington for about two extra alerts a summer.</p>
<p><b>Hidden burden:</b> across %d heat waves, the model attributes %s extra heat-coded calls and %s extra calls with other
heat-related codes, so only about a third of the heat-associated excess (%d%%) is labelled as heat. Raw counts suggest even less
(%d%%). The other calls were above normal in %d of %d heat waves.</p>
<figure>%s
<figcaption>Heat-coded calls per day in the two held-out summers. Black: observed. Blue line and band: expected on a normal-temperature
day, and its normal range. Red circles: alerts. Shaded: heat waves.</figcaption></figure>
<div class="cols"><div>
<h2>What it could mean for Toronto</h2>
<ul>
<li>ECCC warns 18–24 hours ahead for heat events of 2+ days. Paramedic data adds the health side: is heat causing harm, and how
much, including harm not labelled as heat. Single hot days rarely get a warning; the indicator flagged %d%% of them.</li>
<li><b>Plan:</b> aggregated daily Toronto Paramedic Services counts by call type; humidex; Toronto&#39;s 158 neighbourhoods.
Open question: does Toronto&#39;s dispatch record a heat or exposure code? If not, the other-codes approach carries the signal.</li>
</ul>
</div><div>
<h2>Limits</h2>
<ul>
<li>Dispatch codes record what callers and crews report, not diagnoses.</li>
<li>The other-codes excess is noisy: below normal in %d of %d heat waves; 2021–22 baselines are pulled down by 2020.</li>
<li>Three held-out heat waves. NYC data, one weather station; not yet tested in Toronto.</li>
</ul>
</div></div>
</main></body></html>',
  by,
  get("heldout", "indicator", "detected"), get("heldout", "indicator", "heat_waves"),
  get("development", "indicator", "detected"), get("development", "indicator", "heat_waves"),
  round(100 * hb_all$share_coded_model), round(100 * hb_all$share_model_lo), round(100 * hb_all$share_model_hi),
  get("development", "indicator", "false_alarms_per_summer"), lag,
  format(last, "%B %Y"), per_year,
  row("This indicator", "indicator"), row("Farrington Flexible", "farrington"), ears_row,
  hb_all$heat_waves, format(hb_all$heat_model, big.mark = ","), format(hb_all$syndrome_model, big.mark = ","),
  round(100 * hb_all$share_coded_model), round(100 * hb_all$share_coded_observed),
  hb_all$waves_syndrome_excess_positive, hb_all$heat_waves, fig,
  round(100 * get("development", "indicator", "hot_single_days_flagged")),
  hb_all$heat_waves - hb_all$waves_syndrome_excess_positive, hb_all$heat_waves)
writeLines(html, "docs/summary.html")

browsers <- c("Google Chrome.app/Contents/MacOS/Google Chrome", "Chromium.app/Contents/MacOS/Chromium",
              "Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "Brave Browser.app/Contents/MacOS/Brave Browser")
chrome <- Filter(function(f) nzchar(f) && file.exists(f),
                 c(file.path("/Applications", browsers), file.path(path.expand("~/Applications"), browsers),
                   Sys.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome"),
                   Sys.which(c("chromium", "google-chrome", "microsoft-edge"))))
if (length(chrome)) {
  system2(chrome[1], c("--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                       paste0("--print-to-pdf=", normalizePath("docs"), "/summary.pdf"),
                       paste0("file://", normalizePath("docs/summary.html"))), stdout = FALSE, stderr = FALSE)
  cat("wrote docs/summary.pdf\n")
} else {
  # No Chromium-based browser (e.g. Safari only): open the page; in Safari use File > Export as PDF.
  cat("wrote docs/summary.html - opening it; in Safari use File > Export as PDF, save as docs/summary.pdf\n")
  if (interactive() || Sys.getenv("RSTUDIO") == "1") browseURL(normalizePath("docs/summary.html"))
}
