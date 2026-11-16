# EMS Heat Watch

Proof-of-concept heat surveillance from EMS dispatch data. Source: NYC EMS Incident Dispatch Data
(Socrata `76xm-jjuj`). Goal: show heat-associated EMS demand within days instead of the ~6 month lag of
hospital data, as a portfolio piece and a demo for public health units (e.g. Toronto Public Health).
Owner is an epidemiologist/data scientist: be direct, concise, don't over-explain epi or stats basics.

## Layout
- `emsheat/ingest.py`  stream JSON/CSV exports into daily aggregates (`type_daily`, `zip_daily`) + `state.json` watermark.
- `emsheat/fetch.py`   Socrata download, keyset-paged and resumable; `probe` lists live call types.
- `emsheat/weather.py` Open-Meteo / NOAA / CSV daily Tmax.
- `emsheat/model.py`   threshold heat model (lags 0-3), quasi-Poisson; prospective weekly-refit surveillance; zip SIRs.
- `emsheat/analyze.py` orchestration; `emsheat/report.py` single-file HTML report; `emsheat/__main__.py` CLI.
- `synth/`             synthetic NYC-schema data with known effects, truth check, zip power simulation.

## Commands
```
python -m emsheat probe
python -m emsheat fetch --store store --since 2019-01-01 --zip-since 2022-01-01
python -m emsheat analyze --store store --out report --heat-regex "^HEAT$"
python synth/make_synthetic.py && python synth/check_truth.py   # end-to-end test against known truth
```

## Facts to keep in mind
- NYC has a dedicated `HEAT` final call type (~850 calls/yr). `HYPTN`, `COLD`, `SHOT` are NOT heat codes.
- The NYC portal refreshes in batches (latest record was 2026-09-30 on 2026-11-14), so it is not live.
- Validation so far is synthetic only. The first run on real NYC data has not been reviewed yet: check call-type
  stability 2019-2024, the 2025 and 2026 heat waves, and which types the heat-sensitivity screen flags.
- Mar-Jul 2020 is excluded from all fits (COVID).
- Keep all fetch/ingest runs on the same `--zip-since`.
- The sandbox where this was built could not reach NYC Open Data; the fetch code was tested against a mock API only.
- No docx output. Prefer pastable text or artifacts.

## How to report back
- End every summary with a "What you do next" section: numbered steps with exact, copy-pasteable commands
  (one command per fenced bash block), written for the owner's Mac (project at ~/Documents/ems_heat, venv in .venv,
  `export SSL_CERT_FILE="$(python -m certifi)"` before network calls). Say what output to expect or paste back.
