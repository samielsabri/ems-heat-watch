# EMS Heat Watch

Can paramedic data give early warning of heat's health impact, and measure the burden that heat-coded records
miss? A proof of concept on public New York City data.

- **Early warning:** an indicator built on NYC's *heat* call type flagged 19 of 20 heat waves in 2016–2024 and
  all 3 in 2025–2026 (held out, not used to build it), each on the first day, with about 2 alerts per summer
  outside heat waves.
- **Hidden burden:** only about a third of the excess paramedic calls during heat waves carry a heat code
  (34%, 95% CI 26–41%, 23 heat waves). The rest are coded as unconscious, sick, breathing, cardiac and similar.
- **Timeliness:** hospital and mortality data arrive months after a heat event. Paramedic data exist the same day.

One-page summary: [docs/summary.pdf](docs/summary.pdf) · Interactive dashboard:
https://samielsabri.me/dashboards/ems_heat_watch/ems_heat_watch.html

## How it works

1. **Data** (`R/01_get_data.R`): from NYC Open Data, daily counts since 2010 of calls coded *heat*, and of
   heat-related calls with other codes, chosen in advance (unconscious, altered mental status, sick, breathing
   difficulty, cardiac, respiratory, arrest, including the variant codes NYC added in 2020–23). Daily maximum
   temperature at Central Park from NOAA. Both files are in `data/`, so this step is optional.
2. **Early warning** (`R/02_analysis.R`): every week, a Poisson regression is fitted to the previous three years
   (season, day of week, trend, temperature above a threshold). For each day it gives the number of heat calls
   expected if the temperature were normal for that date. An alert is raised when calls exceed the 99.5% upper
   limit of that expectation. The period 2016–2026 is replayed day by day on past data only, and every heat wave
   (3+ days at 32.2 °C or more) is scored. The comparison methods are Farrington Flexible, the standard
   aberration-detection method for routine communicable disease surveillance, and the CDC's EARS C1–C3, both
   from the R `surveillance` package.
3. **Hidden burden** (same script): the same model is fitted to the other heat-related calls. During each heat
   wave and the three days after, the excess over a normal-temperature day is compared between heat-coded calls
   and the other calls.
4. **Summary** (`R/03_summary.R`) and **dashboard data** (`R/04_dashboard_data.R`, which also updates the copy in
   the website repo when it sits next to this one).

## Results

| Method | Heat waves flagged, 2016–24 | Alerts per summer outside heat waves | 2025–26 (held out) | Alerts per summer |
|---|---|---|---|---|
| This indicator | 19/20 | 1.8 | 3/3 | 2.1 |
| Farrington Flexible | 17/20 | 0.3 | 3/3 | 0.0 |
| EARS C1–C3 | 15–18/20 | 4.4–7.3 | 2–3/3 | 2.1–8.3 |

The indicator catches more heat waves than Farrington for about two extra alerts a summer. Alerts come on the
first day of a heat wave because heat calls rise the same day the heat arrives, so it confirms harm as it happens
rather than predicting heat. It also flagged 49% of single hot days (2016–24), which rarely get a heat warning
because warnings are issued for events of two or more days.

| Hidden burden, 23 heat waves (2016–2026) | Heat-coded calls | Other heat-related calls | Share coded as heat |
|---|---|---|---|
| Model estimate of excess | 2,752 | 5,470 | 34% (95% CI 26–41%) |
| Observed excess | 3,379 | 16,364 | 17% |

The model estimate is the more stable of the two. The observed excess in the other calls is noisy: it was below
normal in 3 of 23 heat waves, and the 2021–22 baselines are pulled down by low call volumes in 2020. Full results:
`output/backtest.csv`, `output/hidden_burden.csv`, `output/hidden_burden_by_wave.csv`.

## Run it

```bash
Rscript -e 'install.packages(c("jsonlite", "surveillance"))'
Rscript R/01_get_data.R              # optional, refreshes data/
Rscript R/02_analysis.R              # about 3 minutes
Rscript R/03_summary.R              # writes docs/summary.pdf if Chrome is installed
Rscript R/04_dashboard_data.R       # updates the dashboard data (local and website copy)
```

In RStudio: open `ems-heat-watch.Rproj`, then open each script in `R/` and click Source.

## Limits

- Dispatch codes record what callers and crews report, not diagnoses.
- Only three heat waves fall in the held-out period, and heat waves are defined from temperature alone.
- One weather station and maximum temperature only; Toronto's heat warnings also use humidex.
- NYC's public data is released in batches, about six weeks behind. A health unit working with its own
  paramedic service could get the same counts daily.

## Sources

- NYC EMS Incident Dispatch Data: https://data.cityofnewyork.us/d/76xm-jjuj
- NOAA GHCN-Daily, Central Park (USW00094728): https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily
- Heat warnings in Canada (ECCC): https://www.canada.ca/en/services/environment/weather/severeweather/extreme-heat-warning.html
- Toronto Heat Relief Strategy: https://www.toronto.ca/community-people/health-wellness-care/health-programs-advice/hot-weather/about-torontos-heat-relief-strategy/
