# EMS Heat Watch: proof of concept

A pipeline that turns raw EMS dispatch records into daily heat surveillance. Public health units then see heat-associated EMS demand within a day, instead of waiting about six months for hospital data.

It is built on NYC's public EMS Incident Dispatch Data (Socrata `76xm-jjuj`). The code is source-agnostic: any EMS feed with a timestamp, call type and area code fits the same schema. Toronto Paramedic Services data would be one such feed.

```
raw EMS rows (JSON/CSV, millions)                     weather (Open-Meteo / NOAA / CSV)
        │  ingest: streamed, chunked                          │
        ▼                                                     ▼
daily store: date × borough × call type,    ──►  heat models ──►  alarms, backtest, forecast,
             date × zip × call type                              zip ratios, report.html
        ▲
        │  fetch/update: incremental since watermark (re-pulls last 3 days for late edits)
```

## Quick start on real NYC data

```bash
pip install -r requirements.txt

python -m emsheat probe                        # latest record + call-type list (HEAT is the NYC heat code)
python -m emsheat fetch --store store --since 2019-01-01 --zip-since 2022-01-01   # first pull, resumable
python -m emsheat analyze --store store --out report --heat-regex "^HEAT$"
# refresh later (re-pulls the last 3 days from the watermark; reuse the same --zip-since):
python -m emsheat update --store store --out report --zip-since 2022-01-01 --heat-regex "^HEAT$"
```

Notes:
- `fetch` is resumable: rerun the same command after a crash and it continues from the last saved page in `raw/`. `--fresh` discards saved pages.
- Always pass the same `--zip-since` on every `fetch`, `update` and `ingest`. A batch whose dates all fall before `--zip-since` replaces those dates' zip rows with nothing.
- macOS python.org installs may need `export SSL_CERT_FILE="$(python -m certifi)"` for HTTPS.

If you already downloaded an export (JSON from the `query.json` link or the CSV), skip `fetch`:

```bash
python -m emsheat ingest --store store path/to/export.json      # or .csv, .json.gz, or a folder of pages
```

Optional: set `SOCRATA_APP_TOKEN` for higher API rate limits. Use `--weather noaa` to take Central Park station data instead of Open-Meteo.

## What it produces (`report/`)

- **report.html**: one self-contained file. It shows:
  - the operational view: the last 60 days, today's alarm status, and a 7-day heat-call outlook from the weather forecast;
  - a prospective backtest of every heat wave;
  - exposure-response by outcome and the call-type screen;
  - zip-level ratios.
- **summary.md**: plain-text summary for pasting into a briefing.
- **CSVs**: surveillance series per outcome, heat-wave backtests, call-type screen, and zip ratios.

## Method

| Step | What |
|---|---|
| Outcomes | (1) Heat-coded calls: dispatch codes matching `--heat-regex`. (2) Heat-sensitive syndrome: call types whose heat effect has FDR q < 0.05 in the training years. (3) All calls. (4) Life-threatening calls (FDNY segments 1–3). |
| Exposure-response | Quasi-Poisson time series: spline of time (7 df/yr) + day of week + holidays + threshold heat term over lags 0–3. T0 is chosen by profile deviance. |
| Surveillance | Every week, fit trend + 3 harmonics + day of week + holidays + heat on the previous 3 years, then predict forward. An alarm fires when observed calls exceed the 99.5% negative-binomial limit of the seasonal (no-heat) expectation. |
| Forecast | The same model applied to Open-Meteo forecast temperatures gives expected heat-attributable calls for the next 7 days. |
| Where | Zip-level indirect standardisation: observed vs expected during heat waves, with expected from each zip's share on ordinary summer days. Pooled across waves. |
| Exclusions | Mar–Jul 2020 (COVID disruption). |

## Validation on synthetic data

Everything was tested on 730k synthetic records (regenerate with `synth/make_synthetic.py`; generated data is not committed) in the exact NYC schema, with known effects (`synth/`). The NYC portal is not reachable from the build environment.

- Ingest gives identical aggregates from JSON and from CSV export format. Re-ingesting the same batch leaves the store unchanged.
- Call-type screen: 4 of 7 truly heat-sensitive types were detected with no false positives. The three missed have true effects of 1–2% per °C.
- Model-predicted heat calls over 2024–25 match the true heat-attributable count:
  - heat-coded calls: 98% of true, daily r = 0.99;
  - syndrome: 106% of true, daily r = 0.99;
  - all calls: 99% of true, daily r = 0.97.
- False alarm rate was under 1% on days with no true heat effect. All 7 evaluated heat waves alarmed for heat-coded calls, with a median first alarm on day 1.
- Zip ratios are at chance at synthetic volume (AUC 0.61). A separate power simulation (`synth/zip_power.py`) gives pooled AUC 0.62 / 0.75 / 0.83 / 0.94 at 150 / 600 / 1,500 / 4,000 heat-sensitive calls a day. The method works, but neighbourhood signals need city-scale volume or several seasons.

Reproduce:

```bash
python synth/make_synthetic.py
python -m emsheat ingest --store out/store data/synthetic/ems_2021_2024.json.gz --zip-since 2021-01-01
python -m emsheat ingest --store out/store data/synthetic/ems_2025_update.json.gz --zip-since 2021-01-01
python -m emsheat analyze --store out/store --out out/report \
  --weather-csv data/synthetic/weather_synthetic.csv --asof 2025-07-21 --eval-start 2024-01-01
python synth/check_truth.py
```

## Limits

- Dispatch codes are caller and crew impressions, not diagnoses. The outcome is heat-associated EMS demand.
- How "live" the system is depends on the publisher. The NYC portal appears to refresh in batches. The pipeline handles any cadence, but cannot be fresher than its source.
- One citywide temperature series is used. Heat-island exposure enters only through the zip ratios.
- The threshold model is a simplification of a full DLNM (R `dlnm`).
- Alarm limits ignore parameter uncertainty (a Farrington-style correction would add it).

## Adapting to Toronto

Map the Toronto Paramedic Services fields onto `incident_datetime`, `final_call_type` (or the CTAS/MPDS determinant), `initial_severity_level_code`, `zipcode` (FSA) and `borough` (ward or health region) in `ingest.KEEP`/`ALIASES`. Set the weather point to Toronto (Pearson or City station) in `weather.py`. Set `--heat-regex` to the heat/environmental determinant codes. Everything downstream is unchanged.
