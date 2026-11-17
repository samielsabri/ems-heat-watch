# Figure and one-page summary, built from output/.
#   docs/figure.svg, docs/summary.html, and docs/summary.pdf if Chrome or Chromium is installed
# Usage: Rscript R/03_summary.R ["Name"]   (or Source it in RStudio)

args <- commandArgs(trailingOnly = TRUE)
author <- if (length(args)) args[1] else "Sami El Sabri"
dir.create("docs", showWarnings = FALSE)
ind <- read.csv("output/daily_indicator.csv", colClasses = c(date = "Date"))
waves <- read.csv("output/heat_waves.csv", colClasses = c(start = "Date", end = "Date"))
bt <- read.csv("output/backtest.csv")
heat <- read.csv("data/heat_calls.csv", colClasses = c("Date", "integer"))

# --- figure: heat calls in the two held-out summers ---
ink <- "#0b0b0b"; blue <- "#2a78d6"; red <- "#e34948"; wave <- "#fbe6d6"; grey <- "#6b6a66"
svg("docs/figure.svg", width = 7.5, height = 2.1, family = "Helvetica")
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
ears_row <- sprintf("<tr><td>EARS C1–C3 (CDC)</td><td>%s/%d</td><td>%s</td><td>%s/%d</td><td>%s</td></tr>",
  rng("development", "detected"), get("development", "indicator", "heat_waves"),
  rng("development", "false_alarms_per_summer", "%.1f"),
  rng("heldout", "detected"), get("heldout", "indicator", "heat_waves"), rng("heldout", "false_alarms_per_summer", "%.1f"))
last <- max(heat$date)
lag <- as.numeric(Sys.Date() - last)
per_year <- 10 * round(0.1 * mean(tapply(heat$heat_calls, format(heat$date, "%Y"), sum)[as.character(2016:2024)]))
by <- if (nzchar(author)) paste0(author, " · ") else ""
fig <- paste(readLines("docs/figure.svg"), collapse = "\n")

html <- sprintf('<!doctype html><html><head><meta charset="utf-8"><title>EMS Heat Watch</title><style>
@page { size: Letter; margin: 0.4in 0.55in; }
body { font-family: "Helvetica Neue", Arial, sans-serif; color: #0b0b0b; font-size: 9.4pt; line-height: 1.33; margin: 0; }
h1 { font-size: 18pt; margin: 0 0 2px; } h2 { font-size: 10.5pt; margin: 9px 0 3px; }
.sub { color: #52514e; margin: 0 0 12px; } p { margin: 3px 0 6px; } ul { margin: 3px 0 6px 18px; padding: 0; } li { margin-bottom: 3px; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 6px 0 4px; }
.tile { border: 1px solid #e4e2dc; border-radius: 6px; padding: 8px 10px; } .tile b { display: block; font-size: 16pt; }
.tile span, .note { color: #52514e; font-size: 8.6pt; }
table { border-collapse: collapse; width: 100%%; font-size: 9.2pt; } th, td { padding: 3px 6px; border-bottom: 1px solid #eee; text-align: right; }
th:first-child, td:first-child { text-align: left; } th { color: #52514e; font-weight: 600; }
svg { width: 100%%; height: auto; }
</style></head><body>
<h1>EMS Heat Watch</h1>
<p class="sub">Can ambulance calls show the health impact of heat within days? A proof of concept on public New York City data. %sgithub.com/samielsabri/ems-heat-watch</p>
<div class="tiles">
<div class="tile"><b>%d of %d</b><span>recent heat waves (2025–26, held out) flagged on their first day</span></div>
<div class="tile"><b>~%.0f per summer</b><span>false alarms on ordinary summer days (2016–24)</span></div>
<div class="tile"><b>%d days</b><span>lag of NYC&#39;s public data today, vs months for hospital and mortality data</span></div>
</div>
<h2>Why</h2>
<p>The health impact of heat is usually measured with hospital and mortality data that arrive months later. Ambulance
dispatch data exist in near real time in every paramedic service, but are rarely used for heat surveillance.</p>
<h2>What I did</h2>
<ul>
<li><b>Data:</b> daily counts of NYC ambulance calls coded <i>heat</i> (about %d a year), 2010 to %s, and daily maximum
temperature at Central Park.</li>
<li><b>Indicator:</b> each day, compare heat calls with the number expected on a normal-temperature day at that time of year.
Alarm when calls are above the expected range.</li>
<li><b>Test:</b> replay 2016–2026 day by day, using only past data, and check every heat wave (3+ days at 32 °C or more).
Compare with two standard outbreak-detection methods. Nothing was tuned on 2025–26.</li>
</ul>
<h2>Results</h2>
<table><tr><th>Method</th><th>Heat waves flagged, 2016–24</th><th>False alarms / summer</th><th>2025–26</th><th>False alarms / summer</th></tr>
%s%s%s</table>
<p class="note">Analysis in R; Farrington and EARS from the <i>surveillance</i> package. False alarms are counted on cool summer days.</p>
%s
<p class="note">Black: heat calls per day. Blue: expected on a normal-temperature day, with its normal range. Red circles: alarms. Shaded: heat waves.</p>
<h2>What it means for Toronto</h2>
<ul>
<li>Environment and Climate Change Canada warns 18–24 hours ahead for heat events of two or more days. An EMS indicator adds
the health side: is the heat causing harm, and how much? It does not predict heat; it confirms impact the same day.</li>
<li>Single hot days usually get no warning. In NYC the indicator flagged %d%% of them (2016–24).</li>
<li>Next step: the same indicator on Toronto Paramedic Services data, using humidex.</li>
</ul>
<h2>Limits</h2>
<ul>
<li>Dispatch codes record what callers and crews report, not diagnoses.</li>
<li>Only three heat waves in the held-out period. NYC data and one weather station; not yet tested in Toronto.</li>
</ul>
</body></html>',
  by, get("heldout", "indicator", "detected"), get("heldout", "indicator", "heat_waves"),
  get("development", "indicator", "false_alarms_per_summer"), lag, per_year, format(last, "%B %Y"),
  row("This indicator", "indicator"), row("Farrington Flexible", "farrington"), ears_row, fig,
  round(100 * get("development", "indicator", "hot_single_days_flagged")))
writeLines(html, "docs/summary.html")

chrome <- Filter(file.exists, c("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                                Sys.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome"),
                                Sys.which(c("chromium", "google-chrome"))))
if (length(chrome)) {
  system2(chrome[1], c("--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                       paste0("--print-to-pdf=", normalizePath("docs"), "/summary.pdf"),
                       paste0("file://", normalizePath("docs/summary.html"))), stdout = FALSE, stderr = FALSE)
  cat("wrote docs/summary.pdf\n")
} else cat("wrote docs/summary.html (open it in a browser and print to PDF)\n")
