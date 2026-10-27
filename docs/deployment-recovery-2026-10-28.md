# Deployment recovery — 28 October 2026

## Cause

The supplied midnight log shows repeated INTERMAGNET connection resets (`ConnectionResetError 10054`). TUC and KNY could not obtain the required raw measurements, so `pra_nighttime.py` correctly returned failure. The master workflow then stopped before earthquake integration, export and publication. This was a download failure, not a threshold-fitting failure or a SYM-H skip.

The failure handler waited for “Press Enter to exit,” leaving the registered `GEMPRA` task Running (`0x41301`) after processing had finished. The batch wrapper also paused on both success and failure. Normal INFO logging hid some unprefixed download warnings and the final station summary.

## Changes and impact

- `pra_nighttime.py`: retry the identical station/date request at most three times for connection resets, timeouts, truncated transfers, and HTTP 408/429/500/502/503/504. Retry delays are one and two seconds; the existing 30-second request timeout is unchanged. Permanent request errors, unknown observatories, malformed responses and local write failures do not trigger these retries. Responses are closed after each attempt. Only validated IAGA data replaces the local download, through the existing temporary-file mechanism.
- `logging_utils.py`: retain ordinary operational messages and the station summary at INFO level; recognize the older `Warning:` spelling. Retry and final-failure messages include station and date.
- `deploy_all.ps1` and `deploy_all.bat`: run unattended by default, retain the child exit code, and return without `Read-Host` or `pause`. Direct PowerShell runs may explicitly request `-Interactive`. A failed Pages deployment now returns failure rather than printing a successful workflow summary. The preflight message no longer claims every download succeeded merely because the preflight script finished.
- Regression tests exercise retries, exhausted and permanent failures, input preservation, logging and four real Windows-wrapper paths with inert stages: success, analysis failure, export failure, and deployment failure. `tests/smoke-deployment.cjs` validates the dashboard against its advertised dates without hardcoded historical dates.

No classification is invented if raw magnetic measurements remain unavailable. Exhausted download retries still fail the station and stop publication; the last good deployment is preserved. The stopped instance that was waiting for input was cleared after confirming it had no active child process. The existing task name, action, trigger and daily midnight schedule were retained.

## Scientific preservation

Against source revision `90ee18aa7`, all 26 analysis functions other than `download_data` have identical Python ASTs. This includes `process_station`, the 13-previous-nights-plus-observation threshold selection, EVT/k-sigma formulas, missing-SYM-H quiet assumption, spectral computation, nZ guard, anomaly decision, persistence, cleanup and existing-result protection. Analysis constants/options are identical. Earthquake integration, exporter, publication validator and dashboard sources are also unchanged.

The previous performance and threshold-update reports remain historical records of their respective changes. This operational fix is checked against the immediately preceding source revision; it does not claim that workflow wrapper files remain identical to older revisions.

## Validation

- Python regression suite: 45 tests passed.
- JavaScript dashboard suite: 15 tests passed.
- Both existing Windows workflow wrappers passed the isolated scheduler rehearsal. The new tests additionally verify no-input exits and correct failure propagation.
- Live processing first ran in an independent copy of the current data. TUC completed successfully. KNY reproduced the same connection reset, retried the identical request, then completed successfully. Both recovered October 27 observations contain eight valid hours, no invalid magnetic samples, and no anomalies.

Detailed evidence, input hashes and recovery/deployment logs are retained under ignored `output/dogfood/deployment-2026-10-28/`. Further full-run and publication results are recorded there after validation.

## Full recovery run

- The corrected analysis completed in the independent copy with exit 0: 17 successful station results, 43 unavailable/no-usable-window outcomes, and **zero failed/error stations**. Existing successful observations were reused. Live connection resets at KNY and SPT both recovered on their second attempt.
- Earthquake integration completed with exit 0. Eight individual station/historical catalogue requests timed out during that unchanged integration; its existing query-failure handling remained in effect. All seven final global daily queries succeeded. The exporter and publication validator passed with actual observation dates **22–28 October**.
- The final static-export browser check passed all **357 station/date selections** and **65 scientific-figure links**, plus baseline labels, five viewport widths, theme and refresh/view preservation. No uncaught JavaScript errors or normal-use failed requests were recorded.
- All 1,665 original input files matched their recorded hashes before importing recovered results. Import added only the new KNY/TUC October 27 JSON, CSV and figure files, and appended one date row to each of their existing coverage ledgers. Existing raw measurements and earlier result artifacts were not overwritten or deleted. Coverage-ledger originals and the exact import journal are retained in the evidence folder. Earlier uncommitted station data and retention changes were preserved.
- The recovered KNY baseline uses eight historical nights plus the observation night (68 quiet hours); TUC uses nine plus the observation night (80 quiet hours). These actual counts are retained in their results and displayed by the existing dashboard. Both observations contain eight valid hours and no anomalies.

`candidate-browser/results.json` records the export checks. Publication commit/build checks, hosted-file hashes and public-browser results are recorded separately in the same evidence folder after deployment. This is a recovery run and isolated workflow rehearsal, not a claim that the next scheduled midnight trigger has already executed.
