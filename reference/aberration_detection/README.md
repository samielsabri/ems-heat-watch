# Aberration detection for weekly notifiable-disease surveillance

Prototype comparing statistical outbreak-detection algorithms used by public health
agencies (EARS C1–C3, Farrington Flexible, harmonic quasi-Poisson regression) on
simulated data with known outbreaks, then applying them prospectively to real
surveillance series (e.g. SurvStat@RKI exports).

## Run
```
pip install -r requirements.txt
cd src
python run_simulation.py --n-sims 40 --k 2 4 6 8 --out ../results
python run_real.py --csv ../data/<file>.csv --format survstat --label "Salmonellosis, DE" --out ../results/real
```

## Layout
- `src/simulate.py`: Noufaily et al. (2013) simulation design: NB baseline with trend and Fourier seasonality, outbreaks sized at k × baseline SD with lognormal case spread. Past outbreaks contaminate the reference data.
- `src/detectors.py`: detectors, prospective (each week uses only prior data).
- `src/evaluate.py`: FPR, probability of detection (POD), sensitivity, timeliness.
- `src/run_simulation.py`: simulation study, summary tables, figures.
- `src/run_real.py`: SurvStat / long-CSV loader, alarms per method, cross-method agreement table.

## Known limitations (prototype)
- Farrington Flexible is a numpy reimplementation of `surveillance::farringtonFlexible`
  (NB plug-in threshold, reweighting at 2.58, 26-week guard, 10 seasonal periods).
  Validate against R before publishing results.
- EARS uses a 0.5 minimum SD so all-zero baselines don't alarm on single cases.
- Outbreaks only on the upside; no reporting-delay model yet.
