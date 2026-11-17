# EMS Heat Watch

Proof-of-concept heat surveillance from EMS dispatch data. Source: NYC EMS Incident Dispatch Data
(Socrata `76xm-jjuj`). Goal: show heat-associated EMS demand within days instead of the ~6 month lag of
hospital data, as a portfolio piece and a demo for public health units (e.g. Toronto Public Health).
Owner is an epidemiologist/data scientist: be direct, concise, don't over-explain epi or stats basics.

## Layout
- `emsheat/ingest.py`  stream JSON/CSV exports into daily aggregates (`type_daily`, `zip_daily`) + `state.json` watermark.
- `emsheat/fetch.py`   Socrata: `fetch_aggregates` (server-side daily counts, month cache, resumable; preferred),
                       `daily_counts` (for `verify`), legacy offset-paged row pull; `probe` lists live call types.
- `emsheat/weather.py` Open-Meteo / NOAA / CSV daily Tmax.
- `emsheat/model.py`   threshold heat model (lags 0-3), quasi-Poisson; prospective weekly-refit surveillance; zip SIRs.
- `emsheat/analyze.py` orchestration; `emsheat/report.py` single-file HTML report; `emsheat/__main__.py` CLI.
- `synth/`             synthetic NYC-schema data with known effects, truth check, zip power simulation.

## Commands
```
python -m emsheat probe
python -m emsheat fetch-agg --store store --since 2013-01-01 --zip-since 2022-01-01
python -m emsheat verify --store store
python analysis/run_v2.py --store store --weather-csv data/central_park_tmax.csv --out results/v2
python analysis/make_summary.py --author "Name"                 # one-page PDF in docs/
python -m emsheat analyze --store store --out report --heat-regex "^HEAT$"
python synth/make_synthetic.py && python synth/check_truth.py   # end-to-end test against known truth
```

## Facts to keep in mind
- NYC has a dedicated `HEAT` final call type (~850 calls/yr). `HYPTN`, `COLD`, `SHOT` are NOT heat codes.
- The NYC portal refreshes in batches (latest record was 2026-09-30 on 2026-11-14), so it is not live.
- Real-data run done (results/v2, analysis/run_v2.py): store 2013-01-01..2026-09-30, 20,621,648 calls, matches the
  portal per day. Dev 2016-24, held-out 2025-26 (do not tune on it). Alarm = obs above NB 99.5% limit of the count
  expected at normal Tmax. Syndrome is pre-specified (emsheat/syndromes.py); the screen is exploratory only.
- NYC re-labelled codes (CARDBR from 2017, EDP split, *FC variants 2020-23): merge families via model.merge_variants.
- Mar-Jul 2020 is excluded from all fits (COVID).
- Keep all fetch/ingest runs on the same `--zip-since`.
- Data path: `fetch-agg` (server-side daily aggregates) + `verify`. The row-level keyset `fetch` rewrite was never
  committed and is not recoverable (closed 2026-11-17); row `fetch` is legacy, offset-paged, and no longer deletes raw/.
- Weather: back-test and README numbers use Central Park station Tmax (data/central_park_tmax.csv). `--forecast` appends
  Open-Meteo forecast days to it. `--weather open-meteo` is ERA5 grid history (hotter; different heat waves) - do not mix.
- No docx output. Prefer pastable text or artifacts.

## How to report back
- End every summary with a "What you do next" section: numbered steps with exact, copy-pasteable commands
  (one command per fenced bash block), written for the owner's Mac (project at ~/Documents/ems_heat, venv in .venv,
  `export SSL_CERT_FILE="$(python -m certifi)"` before network calls). Say what output to expect or paste back.
