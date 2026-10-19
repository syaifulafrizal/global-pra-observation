# Local implementation fixes

These changes keep the Python entry points, station catalog, frequency band,
nighttime window, multitaper settings, JSON field names, and existing CSV columns.
No new application dependencies are required. Existing result files, figures,
prepared output, histories, and copyright PDFs are not migrated automatically.

## Run locally

Start or restart the existing local application:

```powershell
python app.py
```

The local application serves the current template and assets together. It builds
dashboard snapshots in memory from canonical station result files, rather than
rewriting prepared output on a page request. The existing analysis commands and
`run_daily_analysis.ps1` still apply. Static output can still be prepared with
`python upload_results.py`.

## Corrected behavior

- INTERMAGNET acquisition requests the service's `XYZF` orientation, validates
  its actual IAGA2002 header, and rejects HTML/error responses. Numeric fill values
  are masked. Missing samples remain on the one-second UTC grid; an hour with
  more than 5% missing samples is excluded. Constant signals are excluded and
  component means are removed before spectral estimation.
- NASA acquisition requests minute-resolution `omni_min`, variable 41 (SYM/H),
  parses that exact column, and normalizes timestamps to UTC. Old caches without
  this provenance are not reused. Missing index data does not count as quiet;
  at least 54 valid minute samples are required to classify an hourly window.
- The GPD fit uses SciPy's shape/location/scale return order and converts the
  overall false-positive target into a conditional tail probability. The
  existing minimum of 30 tail exceedances and k-sigma fallback are retained.
  A six-night historical baseline cannot normally supply enough exceedances
  for EVT; the saved `threshold_method` explicitly reports the fallback.
- Previous screened nights supply the baseline without including the tested
  night. The initial night uses the existing current-night fallback, explicitly
  marked `baseline_source: warmup`. The nZ z-score guard uses previous screened
  vertical powers when at least 20 are available; otherwise its existing fixed
  power guard remains and is identified by `nz_guard_method`.
- Each station processes its latest completed local night. `PROCESS_DATE`
  optionally selects a historical end-of-night date. UTC download days are
  derived from the actual local window. The seven-day initializer now processes
  seven distinct dates in order without enabling forced overwrites.
- Earthquake matches require M>=5 within 200 km in the 14 days after detection.
  The result key uses the local end-of-night date. New anomaly rows record
  `DetectionTimeUTC`; legacy ranges use their local 04:00 end as a conservative
  detection time. `Pending`, `FP`, `TP`, and `Unknown` remain distinct. Failed
  queries cannot establish a false positive.
- `analysis_coverage.csv` retains small per-night coverage records beyond the
  rolling spectral-file retention. A new false-negative classification requires
  14 complete observed nights; missing/invalid observations are not treated as
  successful negative detections. Existing historical records remain preserved
  and are identified as legacy/unverified in the dashboard.
- Output preparation no longer copies a night under the previous date or
  consumes root earthquake input files. Persistent and prepared histories are
  merged without dropping entries. A blank-magnitude status row is never a match.
- Local snapshots expose actual station dates and quality. Legacy constant
  P=0.5 spectra with matching constant vertical/horizontal powers are excluded
  from usable coverage; other old results are marked unverified. Legacy
  backward-looking earthquake matches are unverified until recomputed.
- The chart is labeled **Matched Anomaly Rate**, displays N/A with no anomalies,
  and keeps unavailable/unresolved stations separate. CSV parsing preserves
  quoted place names. Analysis failures return a nonzero process exit code.

## Compatibility and historical data

Existing JSON fields remain. New results add `analysis_version`,
`threshold_method`, `baseline_samples`, `baseline_source`, `nz_guard_method`, and
`data_quality`. New correlation rows retain `days_before_anomaly` and add
`days_after_anomaly` and `detection_time_utc`.

The corrected display may show fewer usable stations and different verified
statistics. This reflects validation of the saved observations; it does not mean
that original files were removed. Historical results are not silently recomputed
or used as a trusted baseline for the corrected algorithm. Keep the supplied PDFs
as historical snapshots; their source hashes describe the pre-fix implementation.

## Verification

```powershell
python -B -m unittest discover -s tests -v
node --test tests/dashboard.test.js
node --check static/app.js
git diff --check
```

Regression tests use temporary fixtures and mocked external requests. A separate
live check processed the KAK night ending 21 December 2025 entirely in a temporary
directory, including NASA context, eight hourly results, CSV, coverage, and PNG.
A browser smoke check exercises the current dashboard, map, theme toggle, and
station selection without regenerating saved data.

Service parameter references:

- https://imag-data.bgs.ac.uk/GIN_V1/
- https://omniweb.gsfc.nasa.gov/form/omni_min.html
- https://omniweb.gsfc.nasa.gov/html/command_line_sample.txt
