# EMS Heat Watch

Proof of concept: daily NYC EMS calls with final call type HEAT (NYC Open Data 76xm-jjuj) as a same-day heat-health
indicator. Portfolio piece for a Toronto Public Health epidemiologist application (posting asks for R/SAS).
Owner is an epidemiologist/data scientist: be direct, concise, don't over-explain epi or stats basics.

## Layout (kept deliberately small; the owner wants a repo that is easy to read and explain)
- `R/01_get_data.R`  daily HEAT counts (SoQL group-by, 2010+) and Central Park Tmax (NOAA GHCN-D) -> data/
- `R/02_analysis.R`  T0 by profile deviance (2013-2024), normal Tmax (harmonics, <=2024), weekly-refit Poisson
                     indicator (3 yrs, alarm = obs > NB 99.5% limit of expected at normal Tmax), Farrington Flexible +
                     EARS C1-C3 from `surveillance`, heat-wave back-test -> output/
- `R/03_summary.R`   docs/figure.svg, docs/summary.html, docs/summary.pdf (headless Chrome if present)
- `R/04_dashboard_data.R` docs/dashboard_data.js for the static dashboard docs/index.html (Plotly 2.35.2 from jsDelivr;
                     GitHub Pages from main /docs). 02_analysis.R writes a day_type column used by the dashboard.
- The earlier Python pipeline (store, HTML report, zip ratios, synthetic tests, call-type screen) lives on branch
  `full-pipeline`. Don't bring it back to main unless asked.

## Facts
- Dev 2016-2024, held out 2025+ (never tune on it). Mar-Jul 2020 excluded. Heat wave = 3+ days Tmax >= 32.2 C.
- Results (R run 2026-11-17): indicator 19/20 dev (1.76 FA/summer), 3/3 held out (2.07); Farrington 17/20 (0.29), 3/3;
  EARS 15-18/20. T0 = 21.5 C (no holiday term). Python version gave the same headline (99.9% daily alarm agreement).
- NYC portal is ~6 weeks behind (batch releases). HEAT counts verified identical to the full 20.6M-row store.
- ECCC: Heat Warnings 18-24 h ahead, events of 2+ days; Toronto criteria Tmax >= 31 & Tmin >= 20, or humidex >= 40
  (toronto.ca). Impact levels Moderate/High/Extreme; no separate "extreme heat warning" product.
- Writing style for anything in the repo: plain, short, human. No docx.

## How to report back
- End every summary with a "What you do next" section: numbered steps with exact, copy-pasteable commands
  (one command per fenced bash block), written for the owner's Mac (project at ~/Documents/ems_heat).
  Say what output to expect or paste back.
