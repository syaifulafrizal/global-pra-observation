# Observation-label clarification — 19 October 2026

All user-facing “unverified” wording has been removed from the dashboard.
SYM-H verification is no longer a condition for the displayed observation label,
and the method strip now describes station-night snapshots.

| Previous wording | Replacement |
|---|---|
| Unverified / Historical result (unverified) | Historical observation |
| Historical observation · screening unverified | Historical observation · no anomaly recorded; coverage not recorded |
| Screened observation, requiring `symh_verified` | Complete observation, based on recorded station-data completeness |
| Legacy / unverified threshold method | Threshold method not recorded |
| Quality status / unverified count | Observation records / complete, partial and historical counts |
| Unverified forecast / Unknown evaluation label | Evaluation unavailable |
| Pending / unverified | Evaluation pending / unavailable |
| Legacy/unverified false-negative records | Historical records · coverage not established |

The wording distinguishes the availability/completeness of measurements from
earthquake evaluation and method metadata. Older files are not relabeled as
complete when they lack completeness information. Existing `unverified` values
in saved aggregate metadata remain readable and are displayed as “historical.”

This is a presentation change. The Python analysis, SYM-H acquisition and
scientific screening, thresholds, anomaly flags, earthquake matching, saved
datasets and scheduler configuration are unchanged. Removing scientific
screening from future calculations would require a separate method change;
the user clarified that the requested change is to dashboard terminology.

Validation includes deterministic tests showing that complete/partial labels
do not depend on `symh_verified`, browser fixtures for missing/false/true
verification, historical measurements, TP/FP/Pending/Unknown evaluations,
all 255 station/date selections, chart-value comparisons, and responsive layouts.
