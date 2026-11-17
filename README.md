# EMS Heat Watch

Heat surveillance from ambulance dispatch data. A proof of concept on New York City's public EMS
Incident Dispatch Data (Socrata `76xm-jjuj`). It is built to show what a near-real-time EMS feed adds
to heat-health surveillance when hospital data arrive about six months late.

**Status (2026-11-16).** First real-data run: NYC, 2013-01-01 to 2026-09-30 (20.6M calls). Exposure is
daily Tmax at Central Park (NOAA GHCN-D USW00094728). Methods were fixed using data to 2024.
2025-01-01 to 2026-09-30 is held out. Every number below comes from `analysis/run_v2.py`, with outputs in
`results/v2/`, unless it is labelled *synthetic*.

## Results on NYC data

**Data.**
- The store holds 20,621,648 calls. Per-day totals match the portal on all 5,021 days (`python -m emsheat verify`).
- The portal is not live. On 2026-11-14 the latest record was 2026-09-30, about 6 weeks behind. That is slow for operations, but still several months ahead of hospital data.
- NYC has a dedicated `HEAT` call type. Its initial and final counts agree within 7% every year.
- Annual HEAT counts follow summer severity: 391 calls in 2014, 1,226 in 2016, 385 in 2020, 1,483 in 2026 through September.
- The peak day was 2026-07-02: 231 calls at Tmax 37.8 °C.

**Exposure-response.** Quasi-Poisson with a time spline, day of week, holidays, and a threshold term
over lags 0-3, fitted 2013-2024 (Mar-Jul 2020 excluded).

| Outcome | Mean/day | T0 (°C) | Change per °C above T0 (95% CI) | Mostly at |
|---|---|---|---|---|
| HEAT calls | 2.2 | 20.5 | +47.8% (+45.9 to +49.8) | lag 0 |
| Heat syndrome, pre-specified* | 1,561 | 15.0 (grid edge) | +1.0% (+0.9 to +1.1) | lag 0 |
| All calls | 4,062 | 15.0 (grid edge) | +0.9% (+0.9 to +1.0) | lag 0 |

\*Syndrome: unconscious, altered mental status, sick, breathing difficulty, cardiac, cardiac/breathing,
respiratory, arrest. Code variants are merged (see `emsheat/syndromes.py`).

For the syndrome and all calls, T0 sits at the lowest value searched. Their association is roughly
log-linear across the warm range, so read T0 there as "no threshold found", not as a heat threshold.

**Back-test.**
- Heat wave: at least 3 consecutive days with Tmax ≥ 32.2 °C (90 °F). There are 20 in development (2016-2024, excluding the COVID period) and 3 held out (2025-06-23, 2025-07-28, 2026-07-01).
- POD: share of waves with at least one alarm between onset and the last hot day.
- False alarms per season: alarms on non-heat days, May-Sep. A non-heat day has Tmax < 29.4 °C that day and the 3 days before, and is away from any wave. The rate is scaled to a 153-day season.
- All methods use a one-sided alpha of 0.005 or their published defaults. Nothing was tuned.

*HEAT calls*

| Method | POD, development | False alarms/season, development | POD, held-out | False alarms/season, held-out |
|---|---|---|---|---|
| Heat model, alarm vs normal-Tmax expectation | 19/20 | 1.8 | 3/3 | 2.1 |
| EARS C1 | 16/20 | 6.5 | 3/3 | 8.3 |
| EARS C2 | 18/20 | 7.3 | 3/3 | 7.2 |
| EARS C3 | 19/20 | 15.6 | 3/3 | 13.4 |
| Farrington Flexible (daily) | 16/20 | 0.0 | 3/3 | 0.0 |

The median delay from wave onset to first alarm is 0 days for every method except Farrington (0.5 days in development).

*Pre-specified heat syndrome*

| Method | POD, development | False alarms/season, development | POD, held-out |
|---|---|---|---|
| Heat model vs normal Tmax | 6/20 | 0.6 | 1/3 |
| EARS C3 | 12/20 | 7.9 | 3/3 |
| Farrington Flexible | 3/20 | 5.6 | 0/3 |

Full tables, including C1, C2 and the "unexplained" alarm: `results/v2/backtest_summary.csv`. Per wave:
`results/v2/backtest_per_wave.csv`.

**How to read this.**
- **HEAT calls are a clean, specific signal.** The heat model detects 19/20 development waves and 3/3 held-out waves, with about 2 false alarms per season. Farrington has no false alarms but misses 4/20. The EARS methods detect as many waves but raise 3-8 times more false alarms.
- **Timeliness is 0 days by construction.** Heat waves are defined from temperature and HEAT calls rise on the same day. So the value is not earlier warning than a thermometer. It is same-day confirmation that heat is causing health harm, and a count of how much.
- **Broad syndromes are too noisy to alarm on daily.** The heat model implies a +3-9% excess for the syndrome over a heat wave. The 99.5% limit sits 13-34% above expected, widest in 2021-22, when training windows include the COVID-era code changes. Observed wave excess ranged from -26% to +28%. Use the syndrome to estimate excess calls, not to raise daily alarms.
- **The call-type screen is exploratory only.** Restricted to codes used throughout training, it flags HEAT, UNC, SHOT and DROWN. SHOT and DROWN show what a data-driven screen picks up: summer behaviour, not heat physiology.

## What the epidemiologist does when it fires (Toronto mapping)

Verified 2026-11-16 on toronto.ca (sources and dates in `docs/toronto_heat_sources.md`):
- Environment and Climate Change Canada (ECCC) issues Heat Warnings for Toronto. TPH stopped issuing its own in 2019.
- A Heat Warning needs a forecast of at least 2 consecutive days with Tmax ≥ 31 °C and Tmin ≥ 20 °C, or at least 2 days with humidex ≥ 40.
- The Heat Relief Network (500+ cool spaces) runs all summer. 24-hour cool spaces and Streets to Homes outreach are part of the response.
- ECCC grades heat alerts by expected impact: Moderate, High, Extreme. Each level's health line runs from "increased" to "higher" to "extreme" risk of illness or death (ECCC weather impact guides). An "Extreme heat warning" product exists, but its meteorological criteria were **not** verified. Check them before citing them.

EMS excess calls measure the health line of those impact levels directly, so the EMS signal can confirm or challenge the impact level assigned to an event.

An EMS alarm is not a weather alert. It is evidence about health impact. The suggested mapping:

| Situation | What the epi does |
|---|---|
| ECCC Heat Warning in effect, EMS heat-coded calls not above the normal-Tmax limit | Routine: report daily counts to the heat response lead. No escalation on EMS grounds. |
| Heat Warning in effect, EMS alarm fires | Confirm (check the data feed, dispatch-code mix, and whether one event drives it). Report excess calls vs normal and the areas most affected to the heat response lead the same day. Use this to argue for extended cool-space hours, targeted outreach, and messaging to high-risk groups. |
| No warning in effect, EMS alarm fires (for example a hot, humid day below criteria) | Treat as a signal of under-forecast impact. Verify, then flag to the heat response lead and ECCC liaison. Log it for the review of warning criteria. |
| After the event | Estimate excess EMS calls for the episode. Compare with the ECCC impact level issued (Moderate/High/Extreme) and with mortality and ED data when they arrive. Feed the result into the annual Heat Relief Strategy review. |

## Method

| Step | What |
|---|---|
| Data | `fetch-agg`: SoQL server-side daily aggregates (date × borough × call type; date × zip × call type from 2022). No row download. It matched row-level ingest exactly on a test day. `fetch` (row pages) and `ingest` remain for exports. |
| Exposure | Central Park daily Tmax, NOAA GHCN-D. Open-Meteo is supported, plus a forecast endpoint for the 7-day outlook. |
| Exposure-response | Quasi-Poisson: natural spline of time (7 df/yr) + day of week + federal holidays + hockey-stick heat term (lags 0, 1, mean of 2-3). T0 by profile deviance over 15-33 °C. |
| Surveillance model | Weekly refit on the previous 3 years: trend, 3 harmonics, day of week, holidays and the heat term. **Alarm:** observed above the NB 99.5% limit of the count expected *at the normal Tmax for that calendar day*. The normal is a harmonic fit to Tmax up to 2024. |
| Comparators | EARS C1, C2, C3 (daily, original form). Farrington Flexible, daily adaptation: 5 reference years, ±7-day window, 10 seasonal periods, 26-week guard, reweighting, no day-of-week term. Both ported from an earlier aberration-detection project. Farrington is not yet cross-checked against R `surveillance`. |
| Exclusions | Mar-Jul 2020 (COVID) from all fits and from scoring. |

## Limitations

- **Dispatch codes are caller/crew impressions, not diagnoses.** The outcome is heat-associated EMS demand.
- **Small held-out set:** 3 heat waves. Development detection rates are partly in-sample: T0 was chosen on 2013-2024.
- **Heat waves are defined from temperature only.** No independent NYC record of heat events (NWS advisories, NYC heat emergencies) has been added yet.
- **Code revisions.** NYC re-labelled codes during the study period: CARDBR from 2017, EDP split from 2018, `*FC` variants 2020-23 (apparently COVID-era). Code families are merged for the syndrome. Any adapter for another jurisdiction needs the same check.
- **One temperature series** (Central Park Tmax). Humidity and humidex are not used yet, although Toronto's criteria use humidex.
- **Simplified exposure model.** The threshold model is a simplification of a DLNM. Its log-linear form above T0 may overstate effects at the extremes.
- **Alarm limits ignore parameter uncertainty.**
- **Zip-level ratios** are underpowered at HEAT-call volume (synthetic power study below). They were not evaluated on real data in v1.
- **Toronto:** whether Toronto Paramedic Services publishes usable call data has not been checked yet. Criteria for a second warning tier are unverified.

## Validation on synthetic data (*synthetic*)

730k synthetic records in the NYC schema, with known heat effects (`synth/`):
- Model-estimated heat-attributable calls vs truth over 2024-25: heat-coded 98% of true (daily r 0.99); pre-specified syndrome 101% (r 0.98); all calls 99% (r 0.97).
- Heat-coded alarms on all 7 injected heat waves, median first alarm on day 1. False alarm rate 0/454 days with no true heat effect.
- Zip ratios are near chance at synthetic volume: pooled AUC 0.65.

Reproduce: see "Commands" below.

## Commands

```bash
pip install -r requirements.txt
# real data (about 1 h for 2013-2026 with zip from 2022; resumable month cache in raw_agg/)
python -m emsheat fetch-agg --store store --since 2013-01-01 --zip-since 2022-01-01
python -m emsheat verify --store store
python analysis/run_v2.py --store store --weather-csv data/central_park_tmax.csv --out results/v2
python -m emsheat analyze --store store --out report --weather-csv data/central_park_tmax.csv \
  --heat-regex "^HEAT$" --train-end 2024-12-31 --eval-start 2025-01-01
# synthetic end-to-end test
python synth/make_synthetic.py
python -m emsheat ingest --store out/store data/synthetic/ems_2021_2024.json.gz --zip-since 2021-01-01
python -m emsheat ingest --store out/store data/synthetic/ems_2025_update.json.gz --zip-since 2021-01-01
python -m emsheat analyze --store out/store --out out/report \
  --weather-csv data/synthetic/weather_synthetic.csv --asof 2025-07-21 --eval-start 2024-01-01
python synth/check_truth.py
```

`data/central_park_tmax.csv` is built from the NOAA GHCN-D station file `USW00094728.csv` (TMAX/10). It can
be refreshed with `emsheat.weather.noaa_central_park`.

## Layout

- `emsheat/`
  - `fetch.py`: rows and server-side aggregates; `verify` reference counts.
  - `ingest.py`: rows → daily store.
  - `weather.py`
  - `model.py`: heat model, normal-Tmax alarm, screen.
  - `aberration.py`: EARS and Farrington.
  - `backtest.py`: heat-wave scoring.
  - `syndromes.py`
  - `analyze.py`, `report.py`: HTML report.
- `analysis/run_v2.py`: the real-data review and back-test above. `run_v1.py` is the first run, kept for the record: its alarm baseline and screen were flawed (see git history).
- `results/v1`, `results/v2`: outputs of those runs.
- `docs/toronto_heat_sources.md`: verified Toronto heat-warning criteria and dates.
- `synth/`: synthetic data with known truth; zip power simulation.
- `reference/aberration_detection/`: source of the EARS and Farrington implementations.
