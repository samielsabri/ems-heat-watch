# EMS Heat Watch

Can ambulance calls show the health impact of heat within days, instead of the months it takes for hospital
and mortality data?

A proof of concept on public New York City data. A simple indicator built on NYC's *heat* call type flagged
19 of 20 heat waves in 2016–2024 and all 3 in 2025–2026, a period that was held out and not used to build it.
It raised about 2 false alarms per summer.

One-page summary: [docs/summary.pdf](docs/summary.pdf)

## The idea

Every paramedic service records its calls in real time. NYC publishes its EMS dispatch data, and one of the
call types is *heat*, about 800 calls a year. If heat calls rise above what a normal day would bring, that
is a same-day signal that heat is harming people.

## How it works

1. **Data** (`R/01_get_data.R`): daily counts of heat calls since 2010 from NYC Open Data, and daily maximum
   temperature at Central Park from NOAA. Both files are in `data/`, so this step is optional.
2. **Indicator** (`R/02_analysis.R`): every week, a Poisson regression is fitted to the previous three years
   (season, day of week, trend, temperature above a threshold). For each day it gives the number of heat
   calls expected if the temperature were normal for that date. An alarm is raised when calls exceed the 99.5%
   upper limit of that expectation.
3. **Test** (same script): the whole period 2016–2026 is replayed day by day, using only past data each
   time. Every heat wave (3+ days at 32.2 °C or more) is scored: was it flagged, and how quickly? False
   alarms are counted on cool summer days. The same is done for two standard outbreak-detection methods,
   Farrington Flexible and EARS C1–C3, from the R `surveillance` package.
4. **Summary** (`R/03_summary.R`): figure and one-page summary in `docs/`.

## Results

| Method | Heat waves flagged, 2016–24 | False alarms per summer | 2025–26 (held out) | False alarms per summer |
|---|---|---|---|---|
| This indicator | 19/20 | 1.8 | 3/3 | 2.1 |
| Farrington Flexible | 17/20 | 0.3 | 3/3 | 0.0 |
| EARS C1–C3 | 15–18/20 | 4.4–7.3 | 2–3/3 | 2.1–8.3 |

Alarms come on the first day of a heat wave, because heat calls rise the same day the heat arrives. So
this does not predict heat; it shows the harm as it happens. The indicator also flagged 49% of single hot
days (2016–24). Those rarely trigger a heat warning, because warnings are issued for events of two or more
days. Full results are in `output/backtest.csv`.

## Run it

```bash
Rscript -e 'install.packages(c("jsonlite", "surveillance"))'
Rscript R/01_get_data.R              # optional, refreshes data/
Rscript R/02_analysis.R              # about 2 minutes
Rscript R/03_summary.R "Your Name"   # writes docs/summary.pdf if Chrome is installed
```

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
