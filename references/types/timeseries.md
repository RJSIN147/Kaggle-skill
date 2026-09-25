# Time-series competitions

Template: `timeseries` — pick it with
`kx new … --template timeseries --template-reason "<why the data is time-ordered>"`
(kx never auto-selects it: the profile cannot tell time order from file stats).

## Walk-forward CV

- `assign_folds(train, y, test)` returns N consecutive validation windows at the end of
  train, in time order; earlier rows are `-1` (train-only). The harness trains fold k on
  every row **before** window k (expanding window) and asserts it, so the CV never sees
  the future. Test predictions come from one model refit on all history.
- Make each window as long as the test horizon (the default measures the test date span).
- `cv.reasoning`: say what the test period is and why the windows mirror it.

## Features

- Build lags and rolling statistics on `concat(train, test)` sorted by time, shifted by
  at least the horizon, so a test row never uses a target it could not have known.
- Calendar features (day of week, month, holidays) are safe.
- Extra files (oil prices, holidays, store metadata) join on keys in `build_features`.

## Metric

For RMSLE fit `log1p(y)` (the default wraps the model in `TransformedTargetRegressor`) and
clip predictions at 0 in `postprocess_submission`.

Live reference: store-sales-time-series-forecasting, calendar-only LightGBM, 3 × 16-day
windows → RMSLE 0.837 ± 0.018 (no lags yet: the obvious next idea).
